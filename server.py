import os
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from math import sqrt

import smtplib
from email.message import EmailMessage
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build

# =========================
# Logging конфигурация
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatvlt")

# =========================
# OpenAI клиент
# =========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Google Calendar конфигурация
# =========================

GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar"]
GCAL_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")  # напр. "primary" или "vvtcamp@gmail.com"


def get_gcal_service():
    """
    Създава Google Calendar service от service account JSON.
    Ако няма конфигурация, връща None и само логва предупреждение.
    """
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_str:
        logger.warning("[GCAL] GOOGLE_SERVICE_ACCOUNT_JSON is not set. Calendar integration disabled.")
        return None

    try:
        info = json.loads(json_str)
        creds = service_account.Credentials.from_service_account_info(info, scopes=GCAL_SCOPES)
        service = build("calendar", "v3", credentials=creds)
        return service
    except Exception as e:
        logger.error(f"[GCAL] Failed to create service account credentials: {e}")
        return None


def parse_iso_utc(dt_str: str) -> Optional[datetime]:
    """
    Приема ISO низ (с или без Z) и връща timezone-aware datetime в UTC.
    """
    if not dt_str:
        return None
    try:
        # Заменяме Z с +00:00, за да може fromisoformat да работи
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(dt_str)

        # Ако има timezone, конвертираме към UTC
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)

        # Ако е naive – приемаме, че вече е в UTC и го маркираме като такъв
        return dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.error(f"[GCAL] Failed to parse appointment_time_utc '{dt_str}': {e}")
        return None


def create_calendar_event_from_appointment(record: Dict[str, object]) -> None:
    """
    Създава събитие в Google Calendar от appointment запис.
    Използва appointment_time_utc, ако е подадено; иначе fallback към +1 час от сега.
    """
    if not GCAL_CALENDAR_ID:
        logger.warning("[GCAL] GOOGLE_CALENDAR_ID is not set. Skipping calendar event.")
        return

    service = get_gcal_service()
    if service is None:
        return

    name = record.get("name") or "Unknown"
    company = record.get("company") or ""
    email = record.get("email") or ""
    phone = record.get("phone") or ""
    location = record.get("location") or ""
    project_description = record.get("project_description") or ""
    language = record.get("language") or ""
    business_id = record.get("business_id") or ""
    timestamp_utc = record.get("timestamp_utc") or datetime.utcnow().isoformat() + "Z"
    appointment_time_text = record.get("appointment_time_text") or ""
    appointment_time_utc = record.get("appointment_time_utc") or ""

    # Заглавие на събитието
    if company:
        summary = f"VLT DATA – {name} ({company})"
    else:
        summary = f"VLT DATA – {name}"

    # Описание
    description_lines = [
        "New appointment request from ChatVLT.",
        "",
        f"Name: {name}",
        f"Company: {company}",
        f"Email: {email}",
        f"Phone: {phone}",
        f"Location: {location}",
        "",
        "Project description / Reason for appointment:",
        project_description,
        "",
    ]

    if appointment_time_text:
        description_lines.append(f"Requested time (human text): {appointment_time_text}")
    if appointment_time_utc:
        description_lines.append(f"Requested time (UTC ISO): {appointment_time_utc}")

    description_lines.extend(
        [
            "",
            f"Client language: {language}",
            f"Business ID: {business_id}",
            f"Created at (UTC): {timestamp_utc}",
        ]
    )

    description = "\n".join(description_lines)

    # Време на събитието
    start_dt = None
    if appointment_time_utc:
        start_dt = parse_iso_utc(appointment_time_utc)

    if start_dt is None:
        # fallback – както досега: +1 час, но timezone-aware UTC
        start_dt = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(hours=1)

    end_dt = start_dt + timedelta(hours=1)

    # Уверяваме се, че и двата са timezone-aware UTC
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    event_body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),  # напр. 2025-11-29T16:00:00+00:00
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "UTC",
        },
    }

    try:
        event = service.events().insert(calendarId=GCAL_CALENDAR_ID, body=event_body).execute()
        logger.info(f"[GCAL] Event created: {event.get('id')} for appointment {name}")
    except Exception as e:
        logger.error(f"[GCAL] Failed to create calendar event: {e}")


# =========================
# Описания на бизнеса (EN + BG)
# =========================

BUSINESS_DESCRIPTION_EN = """
VLT DATA SOLUTIONS — Building the Backbone of Modern Data Centers Across Europe

VLT DATA SOLUTIONS is a specialized engineering company focused on end-to-end data-center
infrastructure deployment, structured cabling and critical IT environments. We operate across Europe
and support enterprises, colocation providers, cloud platforms and telecom operators in building
and maintaining reliable, high-performance data centers.

We combine hands-on field engineering expertise with strict adherence to international standards
(TIA/EIA, ISO/IEC, EN, BICSI) and best practices for Tier III / Tier IV facilities.

Who we are — Company Profile

VLT DATA SOLUTIONS brings together a team of field engineers, network specialists, project managers
and technical experts with solid experience in:

• Structured cabling (fiber & copper) for data centers and large campus environments
• Rack & containment systems, cold/hot aisle, cable management and labeling
• Power distribution, grounding and bonding, basic electrical works inside racks/rows
• Testing, certification and troubleshooting (OTDR, Fluke DSX, other certifiers)
• Migration, upgrade and expansion projects in live data-center environments
• Ongoing maintenance, smart hands and on-site support for mission-critical systems

We are based in Bulgaria and work across Europe, supporting local and international clients with
deployments, upgrades and long-term service engagements.

What we do — Services & Competences

• Full Data-Center Infrastructure Deployment
We design, install and certify complete data-center physical infrastructure — from incoming fiber
and copper connectivity to structured cabling, racks, containment and patching. Our teams are
trained to work in live environments with strict access rules, change windows and safety policies.

Our scope can include:
- Design and planning of the physical layer (cabling routes, rack layout, containment)
- Fiber optic cabling, splicing, patch panels, trays and patch cords
- Copper cabling (Cat6/Cat6A and above), termination, patch panels, cords
- Racks, cabinets, PDUs, grounding and basic power connectivity
- Labeling, documentation and as-built drawings
- Final testing and certification with professional tools (OTDR, Fluke/DSX)

• Structured Cabling (Fiber & Copper)
We build structured cabling systems for data centers, telecom rooms, campus and office buildings.
This includes backbones, horizontal cabling, MDA/HDA/EDA zones and interconnects between rows
and rooms. We follow international standards and vendor recommendations to ensure long-term
performance, scalability and reliability.

Our capabilities cover:
- Fiber backbone deployment (single-mode and multi-mode)
- High-density fiber panels, cassettes and pre-terminated solutions
- Copper horizontal cabling, patching and cross-connects
- MPO/MTP systems and high-speed links for modern data centers
- Proper dressing, routing and separation of data and power

• Rack & Containment, Cable Management, Power & Grounding
We install and configure racks, cabinets and containment systems (cold/hot aisle), ensuring optimal
airflow, maintainability and scalability. We take care of cable management (vertical / horizontal),
overhead or underfloor routing, color-coding and labeling.

We also handle:
- Basic power distribution inside the rack (PDUs, cabling to equipment)
- Grounding and bonding of racks and metallic infrastructure
- Physical security elements (doors, locks) where required

• Testing, Certification & Troubleshooting
Every installation undergoes rigorous testing and certification. We use professional tools such as
OTDRs, Fluke/DSX and network testers to validate performance, attenuation, NEXT/PSNEXT and
other parameters. We provide final reports that can be attached to infrastructure documentation
and audits.

We also help diagnose and fix problems in existing infrastructure:
- Link failures, high attenuation or intermittent issues
- Physical damage to fiber/copper runs
- Re-labeling and documentation of legacy installations

• Upgrades, Migrations & Ongoing Support
Data centers evolve constantly. We support clients during:
- Technology refresh (new switches, storage, servers)
- Rack reconfiguration, re-cabling and capacity expansion
- Relocation of equipment and rows
- Migration windows with strict timing and rollback plans
- Long-term maintenance and “smart hands” services

We can act as your on-site field team for remote operations, performing routine checks, small
tasks, visual inspections, equipment swaps and other activities that require presence in the data
center.

Our Core Principles: Vision, Mission & Values

• Innovation:
We adopt modern engineering practices, tools and structured approaches to deliver clean, scalable
and audit-ready infrastructure. We are constantly improving our methods and workflows.

• Reliability:
We understand that data centers and core networks are mission-critical. We design and build with
redundancy, safety and long-term reliability in mind.

• Partnership:
We see every project as a long-term partnership. We listen, advise and adapt to the client’s needs.
We are transparent about risks, timelines and constraints and always aim to build trust.

Why work with VLT DATA SOLUTIONS

• Specialized in data-center and critical infrastructure projects
• Hands-on field experience across multiple European countries
• Adherence to Tier III / Tier IV design and implementation principles
• Strong focus on documentation, labeling and testing
• Flexible engagement models (project-based, long-term service, on-demand support)

VLT DATA SOLUTIONS — we build and support the physical backbone of your digital infrastructure.
"""

BUSINESS_DESCRIPTION_BG = """
VLT DATA SOLUTIONS — Гръбнакът на модерните дейта центрове в Европа

VLT DATA SOLUTIONS е специализирана инженерна компания, фокусирана върху изграждане на
дейта център инфраструктура, структурно окабеляване и поддръжка на критични ИТ среди.
Работим в цяла Европа и помагаме на предприятия, колокационни центрове, облачни платформи и
телеком оператори да изграждат и поддържат надеждни, високопроизводителни дейта центрове.

Съчетаваме практически опит на терен със стриктно спазване на международни стандарти
(TIA/EIA, ISO/IEC, EN, BICSI) и принципи за Tier III / Tier IV инфраструктура.

Кои сме ние — Профил на компанията

Екипът на VLT DATA SOLUTIONS включва полеви инженери, мрежови специалисти, проектни
мениджъри и техници с богати знания и опит в:

• Структурно окабеляване (оптика и мед) за дейта центрове и големи кампуси
• Rack & containment системи, cold/hot aisle, кабелен мениджмънт и етикетиране
• Захранване, заземяване и основни електро дейности в рамките на IT инфраструктурата
• Тестване, сертификация и диагностика (OTDR, Fluke DSX и др.)
• Миграция, ъпгрейд и разширяване на действащи дейта центрове
• Дългосрочна поддръжка, smart hands и on-site услуги за критични системи

Базирани сме в България и работим в различни европейски държави, като подкрепяме местни и
международни клиенти с изграждане, разширяване и поддръжка на физическа инфраструктура.

Какво правим — Услуги и компетенции

• Пълно изграждане на дейта център инфраструктура
Проектираме, инсталираме и сертифицираме физическата инфраструктура на дейта центрове —
от входящи оптични и медни връзки, през структурно окабеляване, до шкафове, containment,
patch панели и кабелен мениджмънт.

Нашият обхват включва:
- Проектиране и планиране на физическия слой (маршрути на кабели, layout на шкафове и редове)
- Оптично окабеляване, сплайсване, patch панели, trays, patch cords
- Медно окабеляване (Cat6/Cat6A и нагоре), терминaции, patch панели, cords
- Инсталация на racks, cabinets, PDUs, заземяване и базово захранване
- Етикетиране, документация и as-built чертежи
- Финално тестване и сертификация с професионални уреди (OTDR, Fluke/DSX)

• Структурно окабеляване (оптика и мед)
Изграждаме структурни кабелни системи за дейта центрове, телекомуникационни помещения,
офис сгради и кампуси — включително backbone, хоризонтално окабеляване, MDA/HDA/EDA
зони и междуредови връзки.

Обхватът включва:
- Оптични backbone линкове (single-mode и multi-mode)
- High-density оптични панели, касети и pre-terminated решения
- Медно хоризонтално окабеляване и cross-connect решения
- MPO/MTP системи за високоскоростни дейта център среди
- Коректно разделяне и маршрутизиране на data и power

• Rack & Containment, кабелен мениджмънт, захранване и заземяване
Инсталираме и конфигурираме шкафове, cabinets и containment системи (cold/hot aisle), така че
да осигурим добър въздушен поток, лесна поддръжка и скалируемост. Грижим се за кабелния
мениджмънт (вертикален/хоризонтален), overhead или raised floor решения, color-coding,
labeling и достъпност.

Също така:
- Изграждаме базово захранване в рамките на шкафа (PDUs, кабели към оборудване)
- Осигуряваме заземяване и свързване на металните елементи
- Можем да интегрираме базови физически защити (ключалки, врати) при нужда

• Тестване, сертификация и диагностика
Всяка инсталация преминава през стриктно тестване и сертификация. Използваме професионални
уреди като OTDR, Fluke/DSX и други тестери, за да проверим затихване, параметри като NEXT,
PSNEXT и други. Предоставяме финални отчети, които могат да бъдат прикачени към
документация, одити и compliance изисквания.

Също така помагаме при проблеми в съществуваща инфраструктура:
- Линкове с високо затихване, периодични прекъсвания или пълни откази
- Физически повреди по оптични/медни трасета
- Преетикетиране и документално подреждане на legacy инсталации

• Ъпгрейди, миграции и дългосрочна поддръжка
Инфраструктурата в дейта центровете се развива постоянно. Подкрепяме клиенти при:
- Технологичен refresh (нови суичове, storage, сървъри)
- Реорганизация на шкафове, recabling и увеличаване на капацитета
- Преместване на оборудване и цели редове
- Миграционни прозорци с точни графици и rollback планове
- Дългосрочни договори за поддръжка и „smart hands“ услуги

Можем да бъдем вашият on-site екип за редовни проверки, малки задачи, инспекции, смяна на
оборудване и други дейности, изискващи физическо присъствие в дейта центъра.

Нашите принципи: Визия, мисия и ценности

• Иновация:
Прилагаме модерни инженерни практики, инструменти и структуриран подход при изграждането
на инфраструктура. Винаги се стремим да подобряваме процесите и методите си.

• Надеждност:
Разбираме критичността на дейта центровете и мрежите. Проектираме и изграждаме с фокус върху
резервираност, сигурност и дългосрочна стабилност.

• Партньорство:
Всяко сътрудничество за нас е дългосрочен партньорски ангажимент. Слушаме, консултираме,
споделяме рискове и винаги се стремим да изграждаме доверие.

Защо VLT DATA SOLUTIONS

• Специализация в дейта център и критична инфраструктура
• Практически опит в множество европейски държави
• Принципи на Tier III / Tier IV при дизайн и реализация
• Силен фокус върху документация, етикетиране и тестване
• Гъвкави модели на работа (по проект, дългосрочни услуги, on-demand)

VLT DATA SOLUTIONS — ние изграждаме и поддържаме физическия гръбнак на вашата дигитална инфраструктура.
"""

# =========================
# Бизнес конфигурация
# =========================

BUSINESSES = {
    "vlt_data": {
        "name": "VLT DATA SOLUTIONS",
        "site_url": "https://vltdatasolutions.com",
        "languages": ["bg", "en"],
        "description_en": BUSINESS_DESCRIPTION_EN,
        "description_bg": BUSINESS_DESCRIPTION_BG,
        "tone_bg": "Професионален, спокоен, технически, но разбираем.",
        "tone_en": "Professional, calm and technical, but clear for non-technical people.",
        "search_url_template": "https://vltdatasolutions.com/?s={query}"
    }
}

APPOINTMENT_MARKER = "##APPOINTMENT##"
CONTACT_MARKER = "##CONTACT_MESSAGE##"
SEARCH_MARKER = "##SEARCH_LINK##"


def _clean_text(text: str, max_length: int = 4000) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.split())
    return cleaned[:max_length]


def _is_same_domain(base_url: str, other_url: str) -> bool:
    try:
        base = urlparse(base_url)
        other = urlparse(other_url)
        return base.netloc == other.netloc
    except Exception:
        return False


def crawl_site(business_id: str) -> List[Dict[str, str]]:
    biz = BUSINESSES.get(business_id, BUSINESSES["vlt_data"])
    base_url = biz.get("site_url")
    if not base_url:
        return []

    max_pages = int(os.getenv("MAX_PAGES_PER_SITE", "40"))

    visited = set()
    to_visit = [base_url]
    pages: List[Dict[str, str]] = []

    headers = {"User-Agent": "ChatVLT-Bot/1.0"}

    while to_visit and len(pages) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if "text/html" not in resp.headers.get("Content-Type", ""):
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            title = soup.title.string.strip() if soup.title and soup.title.string else url

            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = _clean_text(text)

            if text:
                pages.append({"url": url, "title": title, "text": text})

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href:
                    continue
                full = urljoin(url, href)
                if "#" in full:
                    full = full.split("#", 1)[0]
                if full in visited or full in to_visit:
                    continue
                if not _is_same_domain(base_url, full):
                    continue
                if any(full.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".rar"]):
                    continue
                to_visit.append(full)
        except Exception:
            continue

    return pages


def embed_text(text: str) -> List[float]:
    if not text:
        return []
    try:
        resp = client.embeddings.create(
            model="text-embedding-3-large",
            input=[text],
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.error(f"[EMBED] Error creating embedding: {e}")
        return []


def build_site_index(business_id: str) -> List[Dict[str, object]]:
    index_filename = f"site_index_{business_id}.json"
    if os.path.exists(index_filename):
        try:
            with open(index_filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.error(f"[INDEX] Error reading index file: {e}")

    pages = crawl_site(business_id)
    index: List[Dict[str, object]] = []
    for p in pages:
        emb = embed_text(p["text"])
        index.append(
            {
                "url": p["url"],
                "title": p["title"],
                "text": p["text"],
                "embedding": emb,
            }
        )

    try:
        with open(index_filename, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[INDEX] Error writing index file: {e}")

    return index


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def find_relevant_pages(business_id: str, query: str, top_k: int = 3) -> List[Dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []

    index = build_site_index(business_id)
    if not index:
        return []

    q_emb = embed_text(query)
    if not q_emb:
        return []

    scored = []
    for item in index:
        emb = item.get("embedding") or []
        sim = _cosine_similarity(q_emb, emb)
        if sim > 0:
            scored.append((sim, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_items = [it for _, it in scored[:top_k]]
    return [
        {
            "url": it["url"],
            "title": it.get("title", it["url"]),
            "text": it.get("text", ""),
        }
        for it in top_items
    ]


def build_site_context_message(business_id: str, user_query: str) -> Optional[str]:
    pages = find_relevant_pages(business_id, user_query, top_k=3)
    if not pages:
        return None

    parts = []
    for p in pages:
        snippet = p["text"][:800]
        parts.append(
            f"URL: {p['url']}\nTITLE: {p['title']}\nCONTENT SNIPPET:\n{snippet}"
        )

    joined = "\n\n---\n\n".join(parts)
    biz_name = BUSINESSES.get(business_id, BUSINESSES["vlt_data"])["name"]
    return (
        "The following is trusted content taken directly from the official website "
        f"of {biz_name}."
        "\nUse it as an additional source of truth for:"
        "\n- product information (names, categories, sizes, models)"
        "\n- contact details (phone, email, address, working hours)"
        "\n- services, managers and team roles"
        "\n- descriptions of pages, sections and policies"
        "\n\nALWAYS include clickable links (the URLs below) in your answer when helpful."
        "\n\n"
        f"{joined}"
    )


def build_system_prompt(business_id: str) -> str:
    biz = BUSINESSES.get(business_id, BUSINESSES["vlt_data"])

    return f"""
You are ChatVLT – an AI assistant for the company {biz['name']}.
Below is the official company description in English and Bulgarian.
Use it as the ONLY trusted source about the company and its services.

[COMPANY DESCRIPTION – EN]
{biz['description_en']}

[ОПИСАНИЕ НА КОМПАНИЯТА – BG]
{biz['description_bg']}

LANGUAGE RULES:
- Detect the language of the user message.
- If the user writes in Bulgarian, answer in Bulgarian.
- If the user writes in English, answer in English.
- Do NOT mix the two languages unless the user explicitly asks you.

STYLE:
- Bulgarian: {biz['tone_bg']}
- English: {biz['tone_en']}
- Be concise but helpful. Explain technical topics in a way that non-technical people can understand,
  but keep the option to go deeper if the user is technical.
- If something is not mentioned in the description, say that you cannot be sure and recommend direct
  contact with the {biz['name']} team instead of inventing facts.

COMPANY VS CLIENT DATA (VERY IMPORTANT):
- You will often receive personal data from the user: their name, email, phone, company.
- NEVER reuse any user-provided personal contact (email, phone, company) as official contact data
  for {biz['name']}.
- If the user asks for official contacts of {biz['name']} (phone, email, address) and such data is
  not explicitly provided in the description above, you MUST say that they can find the official
  contact details on the company's website (vltdatasolutions.com) or via the Contact page.
- It is FORBIDDEN to present the user's email/phone as if it were the company's email/phone.

HANDLING CLIENT COMPANY NAMES:
- When the user says: "My company is X", "We are company X", "Our company is called X",
  treat this as CLIENT INFORMATION for a potential project or lead.
- DO NOT try to describe company X, DO NOT refuse the conversation just because it is not {biz['name']}.
- You only have detailed information about {biz['name']}.

APPOINTMENTS / LEADS (PROJECTS, OFFERS, BOOKINGS):
- If the user is clearly interested in a project, offer, quotation, on-site work, data center build,
  upgrade, migration or maintenance, OR wants to book a specific date/time (like a consultation
  or appointment), you should gently collect contact details.

- Ask naturally (not as a rigid form) for:
  * full name
  * company (if any)
  * email
  * phone (if possible)
  * country/city or site location
  * short description of the project or reason for the appointment
  * preferred date and time for the appointment (ask explicitly!)

- The preferred appointment time should be clarified in conversation, for example:
  "next Monday at 15:00", "tomorrow morning around 10:30", "on 5 December at 14:30",
  "Wednesday after 11:00", etc.

- Once you understand the time, you MUST convert it to:
  * appointment_time_text  – short human-readable description, in the user language
    (for example: "понеделник, 15:30, часова зона Europe/Sofia")
  * appointment_time_utc   – single ISO 8601 string in UTC, e.g. "2025-12-05T13:30:00Z"

- When the user writes in Bulgarian and does not specify timezone, assume Europe/Sofia.
- When the user writes in English and mentions a clear timezone, respect it; otherwise you may
  assume Europe/Sofia if it makes sense (for Bulgarian context) or UTC if unclear.

- Always keep track of what information you already have.
  If some details are missing, ASK ONLY FOR THE MISSING FIELDS, not for everything again.

- As soon as you have AT LEAST:
  * name
  * at least one contact (email OR phone)
  * a short project/appointment description
  * a clarified appointment time

  you MUST:
  1) stop asking for more details,
  2) thank the user and confirm that the {biz['name']} team will review the information
     and confirm the exact time by email/phone,
  3) append at the end of your answer a single line in the format:

  {APPOINTMENT_MARKER} {{
    "name": "...",
    "company": "...",
    "email": "...",
    "phone": "...",
    "location": "...",
    "project_description": "...",
    "language": "bg or en",
    "appointment_time_text": "...",
    "appointment_time_utc": "YYYY-MM-DDTHH:MM:SSZ"
  }}

- The JSON must be:
  * valid,
  * single-line,
  * keys in English,
  * and you must NOT mention this JSON in the visible answer.

CONTACT MESSAGES (GENERAL QUESTIONS / SUPPORT):
- If the user just wants to "send a message", "ask a question" or "write to the team",
  you should collect:
    * name,
    * email,
    * short subject (1 line),
    * message body (their question / request)

- Once you have at least name + email + message text,
  you MUST append at the end of your answer a single line in the format:

  {CONTACT_MARKER} {{
    "name": "...",
    "email": "...",
    "phone": "...",
    "subject": "...",
    "message": "...",
    "language": "bg or en"
  }}

- Again, the JSON must be on a single line, valid, keys in English, and you must NOT mention
  this JSON in the visible answer. Just confirm that the {biz['name']} team will receive the message.

SEARCH LINK HANDLING:
- If the user asks you to "search the site", "show more information from the website",
  "find products/services on the company's site" or similar, you should:
  1) Keep answering normally in natural language.
  2) At the very end, add ONE line with the format:

     {SEARCH_MARKER} {{
       "query": "keywords in English or Bulgarian describing what to search"
     }}

- The "query" should be short but meaningful (e.g. "rack & containment", "fiber cabling", "optical links").
- DO NOT explain this JSON in your answer. It is only for the backend to generate a search URL.

TASK:
- Answer only about data center infrastructure, services and capabilities of {biz['name']}.
- If the user asks something unrelated (weather, politics, random topics),
  politely explain that your role is to assist only with the services and expertise of {biz['name']}.
- For contact or projects, encourage the user to briefly describe their project
  (new data center, upgrade, migration, maintenance) and then collect the data as explained above.
"""


# =========================
# Email helper
# =========================

def send_email(subject: str, body: str, to_email: str) -> None:
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    port_str = os.getenv("SMTP_PORT", "587")
    from_email = os.getenv("SMTP_FROM") or user or to_email

    logger.info(f"[EMAIL] Preparing email to {to_email} with subject '{subject}'")
    logger.info(f"[EMAIL] SMTP_HOST={host}, SMTP_USER={user}, SMTP_PORT={port_str}")

    if not host or not user or not password:
        logger.warning("[EMAIL] Missing SMTP configuration, email will NOT be sent.")
        return

    try:
        port = int(port_str)
    except ValueError:
        port = 587

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            try:
                server.starttls()
                logger.info("[EMAIL] STARTTLS successful.")
            except Exception as e:
                logger.warning(f"[EMAIL] STARTTLS failed or not supported: {e}")
            try:
                server.login(user, password)
                logger.info("[EMAIL] SMTP login successful.")
            except Exception as e:
                logger.error(f"[EMAIL] SMTP login failed: {e}")
                return
            try:
                server.send_message(msg)
                logger.info("[EMAIL] Email sent successfully.")
            except Exception as e:
                logger.error(f"[EMAIL] Sending email failed: {e}")
    except Exception as e:
        logger.error(f"[EMAIL] SMTP connection failed: {e}")


# =========================
# FastAPI приложение
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    business_id: Optional[str] = "vlt_data"
    history: Optional[List[Dict[str, str]]] = None


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ChatVLT"}


def save_appointment(business_id: str, json_str: str) -> None:
    try:
        m = re.search(r"\{.*\}", json_str, re.DOTALL)
        if not m:
            return
        data = json.loads(m.group(0))

        record = {
            "business_id": business_id,
            "timestamp_utc": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            **data,
        }

        with open("appointments.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        to_email = os.getenv("APPOINTMENT_EMAIL_TO")
        logger.info(f"[APPOINTMENT] Saved appointment for business={business_id}, to_email={to_email}")

        if to_email:
            lang = (data.get("language") or "").lower()
            is_bg = lang.startswith("bg")

            if is_bg:
                subject = f"Нова заявка за среща от ChatVLT ({business_id})"
                body_lines = [
                    "Имате нова заявка за среща от ChatVLT.",
                    "",
                    f"Име: {data.get('name') or ''}",
                    f"Фирма: {data.get('company') or ''}",
                    f"Email: {data.get('email') or ''}",
                    f"Телефон: {data.get('phone') or ''}",
                    f"Локация: {data.get('location') or ''}",
                    "",
                    "Описание на проекта / причина за среща:",
                    data.get("project_description") or "",
                    "",
                ]
            else:
                subject = f"New appointment request from ChatVLT ({business_id})"
                body_lines = [
                    "You have a new appointment request from ChatVLT.",
                    "",
                    f"Name: {data.get('name') or ''}",
                    f"Company: {data.get('company') or ''}",
                    f"Email: {data.get('email') or ''}",
                    f"Phone: {data.get('phone') or ''}",
                    f"Location: {data.get('location') or ''}",
                    "",
                    "Project / appointment description:",
                    data.get("project_description") or "",
                    "",
                ]

            if data.get("appointment_time_text"):
                body_lines.append(f"Requested time (human text): {data.get('appointment_time_text')}")
            if data.get("appointment_time_utc"):
                body_lines.append(f"Requested time (UTC ISO): {data.get('appointment_time_utc')}")

            body_lines.extend(
                [
                    "",
                    f"Език на клиента / Client language: {data.get('language') or ''}",
                    f"Business ID: {business_id}",
                    "",
                    f"Време (UTC): {record['timestamp_utc']}",
                ]
            )

            body = "\n".join(body_lines)
            send_email(subject, body, to_email)

        # Google Calendar събитие
        create_calendar_event_from_appointment(record)

    except Exception as e:
        logger.error(f"[APPOINTMENT] Error while saving/sending appointment: {e}")


def save_contact_message(business_id: str, json_str: str) -> None:
    try:
        m = re.search(r"\{.*\}", json_str, re.DOTALL)
        if not m:
            return
        data = json.loads(m.group(0))

        record = {
            "business_id": business_id,
            "timestamp_utc": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            **data,
        }

        with open("contact_messages.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        to_email = os.getenv("CONTACT_EMAIL_TO")
        logger.info(f"[CONTACT] Saved contact message for business={business_id}, to_email={to_email}")

        if to_email:
            lang = (data.get("language") or "").lower()
            is_bg = lang.startswith("bg")

            if is_bg:
                subject = f"Ново съобщение от ChatVLT ({business_id})"
                body_lines = [
                    "Имате ново контактно съобщение от ChatVLT.",
                    "",
                    f"Име: {data.get('name') or ''}",
                    f"Email: {data.get('email') or ''}",
                    f"Телефон: {data.get('phone') or ''}",
                    "",
                    f"Тема: {data.get('subject') or ''}",
                    "",
                    "Съобщение:",
                    data.get("message") or "",
                    "",
                    f"Език на клиента: {data.get('language') or ''}",
                    f"Business ID: {business_id}",
                    "",
                    f"Време (UTC): {record['timestamp_utc']}",
                ]
            else:
                subject = f"New contact message from ChatVLT ({business_id})"
                body_lines = [
                    "You have a new contact message from ChatVLT.",
                    "",
                    f"Name: {data.get('name') or ''}",
                    f"Email: {data.get('email') or ''}",
                    f"Phone: {data.get('phone') or ''}",
                    "",
                    f"Subject: {data.get('subject') or ''}",
                    "",
                    "Message:",
                    data.get("message") or "",
                    "",
                    f"Client language: {data.get('language') or ''}",
                    f"Business ID: {business_id}",
                    "",
                    f"Time (UTC): {record['timestamp_utc']}",
                ]

            body = "\n".join(body_lines)
            send_email(subject, body, to_email)

    except Exception as e:
        logger.error(f"[CONTACT] Error while saving/sending contact message: {e}")


def build_search_url(business_id: str, json_str: str) -> Optional[str]:
    try:
        m = re.search(r"\{.*\}", json_str, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))

        query = data.get("query", "")
        if not query:
            return None

        biz = BUSINESSES.get(business_id, BUSINESSES["vlt_data"])
        template = biz.get("search_url_template")
        if not template:
            return None

        from urllib.parse import quote_plus

        encoded_query = quote_plus(query)
        return template.format(query=encoded_query)
    except Exception as e:
        logger.error(f"[SEARCH] Error while building search URL: {e}")
        return None


# =========================
# /chat endpoint
# =========================

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message.")

    business_id = req.business_id or "vlt_data"
    system_prompt = build_system_prompt(business_id)

    messages = [{"role": "system", "content": system_prompt}]

    if req.history:
        for m in req.history[-10:]:
            role = m.get("role")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    site_context = build_site_context_message(business_id, req.message)
    if site_context:
        messages.append({"role": "system", "content": site_context})

    messages.append({"role": "user", "content": req.message})

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=700,
        )

        raw_reply = completion.choices[0].message.content.strip()
        visible_reply = raw_reply

        # Appointment marker
        if APPOINTMENT_MARKER in visible_reply:
            before, after = visible_reply.split(APPOINTMENT_MARKER, 1)
            visible_reply = before.strip()
            save_appointment(business_id, after.strip())

        # Contact marker
        if CONTACT_MARKER in visible_reply:
            before, after = visible_reply.split(CONTACT_MARKER, 1)
            visible_reply = before.strip()
            save_contact_message(business_id, after.strip())

        # Search marker
        if SEARCH_MARKER in visible_reply:
            before, after = visible_reply.split(SEARCH_MARKER, 1)
            visible_reply = before.strip()
            url = build_search_url(business_id, after.strip())
            if url:
                visible_reply = f"{visible_reply}\n\n👉 Линк: {url}"

        return ChatResponse(reply=visible_reply)

    except Exception as e:
        logger.error(f"[CHAT] Error while generating response: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error while generating response from ChatVLT.",
        )
