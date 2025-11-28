import os
import json
import re
from datetime import datetime
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# =========================
# OpenAI клиент
# =========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Описания на бизнеса (EN + BG)
# =========================

BUSINESS_DESCRIPTION_EN = """
VLT DATA SOLUTIONS — Building the Backbone of the Digital World

Who we are
VLT DATA SOLUTIONS is a European engineering company specializing in the design, installation and maintenance of mission-critical data center infrastructure. Our field teams operate across Europe and deliver complete, certified infrastructure solutions—from structured cabling (fiber & copper), through rack and containment installation, to power distribution, grounding and final system certification — all built to comply with the most demanding reliability standards (Tier III / Tier IV).

We are a team of field engineers, network specialists and technicians dedicated to precision, reliability, safety and long-term performance. Every cable, every splice, patch, rack or power line we install is tested, labelled and documented to guarantee traceability and compliance.

Our vision is to build and support the digital backbone of Europe — enabling organisations, cloud providers and data platforms to run smoothly, securely and efficiently. We stand for innovation, reliability and partnership: not just infrastructure, but trust.

What we offer — Services & Competences

• Full Data-Center Infrastructure Deployment
We design, build and deliver full data-center infrastructure — structured fiber and copper cabling, rack installation and organization, containment systems, power distribution and grounding. Our work covers from early planning and routing to final certification and documentation compliance (Tier III / IV).

• Structured Cabling (Fiber & Copper) & Network Installation
Our teams perform fiber splicing, copper terminations, cable management, labelling, patching, and testing (OTDR for fiber; Fluke / DSX certification for copper). We guarantee certified, high-quality connectivity for mission-critical networks.

• Rack & Containment Installation, Cable Management & Power Systems
We deploy racks, cable containment, PDUs / power distribution systems, grounding and backup paths. We also take care of airflow planning, U-space balancing, and layout optimization for efficient maintenance and future scalability.

• Testing, Certification & Documentation
Every installation undergoes rigorous testing — network certification, grounding/bonding verification, redundancy and failover planning. All results are documented, labelled and handed over, ensuring compliance, traceability and long-term reliability.

• Consulting, Upgrade & Maintenance Services
Whether you plan a new data-center build, an upgrade, relocation or infrastructure maintenance — we provide site surveys, capacity planning, route design, materials selection, installation and on-site maintenance. Our goal is to ensure infrastructure remains stable, scalable and efficient over time.

• Scalable & Future-Proof Infrastructure
We build with scalability, safety, redundancy and modular design in mind — so infrastructure can evolve with clients' needs. From dual-path cabling, redundant power, containment, expandability and maintenance-friendly layout — we deliver durable solutions for the long run.

Our Core Principles: Vision, Mission & Values

• Innovation:
We bring modern engineering methods and state-of-the-art technologies (fiber optics, certified cabling, advanced power and containment solutions) to build data-centers ready for tomorrow’s demands.

• Reliability:
Every connection and installation is built to last — tested, certified and documented following international standards. We guarantee uptime, safety and stability even under heavy load and critical conditions.

• Partnership:
We work closely with our clients — transparent communication, professional execution and shared responsibility. Our success is measured by their long-term satisfaction and infrastructure performance.

• Quality & Compliance:
Compliance with Tier III / Tier IV standards, rigorous testing, documentation and safety procedures are fundamental. We don’t cut corners — everything is done with precision, traceability and accountability.

Contact & Support
If you are planning a new data-center build, upgrade, relocation or infrastructure optimization — our team is ready to assist. We operate across Europe and deliver infrastructure tailored to your workload, growth plans and reliability requirements.
"""

BUSINESS_DESCRIPTION_BG = """
VLT DATA SOLUTIONS — Строим дигиталната основа на бъдещето

Кои сме ние
VLT DATA SOLUTIONS е европейска инженерна компания, специализирана в проектиране, изпълнение и поддръжка на критична инфраструктура за дата центрове. Нашите екипи оперират в цяла Европа и предоставят цялостни, сертифицирани решения — от структурно окабеляване (оптика и мед), през инсталация на шкафове (racks), containment, електрозахранване, заземяване и финална сертификация — всичко според най-високи изисквания за надеждност (Tier III / Tier IV).

Ние сме екип от инженери, мрежови специалисти и техници, за които прецизността, безопасността и дългосрочната работа са основен приоритет. Всеки кабел, всяка връзка, всеки сплайс, шкаф или захранване се тества, етикетира и документира — за пълна проследимост и качество.

Нашата визия е да изградим и поддържаме дигиталната „гръбнака“ на Европа — да дадем на организации, облачни доставчици и платформи инфраструктура, която работи гладко, сигурно и ефективно. Нашите ценности са: иновация, надеждност и партньорство — не просто инфраструктура, а дългосрочна сигурност и доверие.

Какво предлагаме — услуги и компетенции

• Цялостно изграждане на дата-център инфраструктура
Проектираме и изграждаме цялостна дата-център инфраструктура — структурно окабеляване (оптика и мед), монтаж на шкафове (racks), containment системи, разпределение на ток, заземяване. Покриваме целия процес — от планиране и маршрути, до финална сертификация и документация според Tier III / IV.

• Структурно окабеляване и мрежова инсталация (fiber & copper)
Нашите екипи извършват splice на оптични влакна, медно окабеляване, patchи, организация на кабели, етикетиране и тестване (OTDR за оптика; Fluke / DSX сертификация за мед), за да гарантираме високо качество и сигурност на мрежата.

• Монтаж на шкафове, containment, управление на кабели и захранване
Инсталираме racks, containment, PDU / разпределение на ток, заземяване и резервни пътища. Планираме въздушен поток, баланс на пространството (U-space), оптимизация на layout за лесна поддръжка и скалируемост.

• Тестване, сертификация и документация
Всяка инсталация преминава през строг тестинг — сертификация на мрежата, проверка на заземяване и връзки, планове за резервираност и failover. Всичко се документира, етикетира и се предава на клиента, гарантирайки устойчивост, проследимост и качество.

• Консултации, ъпгрейди и поддръжка
Ако планирате нов проект, ъпгрейд на съществуваща инфраструктура, преместване или поддръжка — ние предлагаме огледи, проектиране, материали, инсталация и onsite поддръжка. Нашата цел е инфраструктурата да бъде стабилна, скалируема и ефективна през целия ѝ живот.

• Скалируема и бъдеща инфраструктура
Проектираме така, че инфраструктурата да расте с вашите нужди: двойни пътища (dual-path), резервираност, modularни системи, резервни захранвания, containment и layout, които позволяват лесна поддръжка, ъпгрейди и експанзия.

Нашите принципи — визия, мисия и ценности

• Иновация:
Прилагаме модерни инженерни практики и технологии — оптични влакна, сертифицирани кабели, съвременни power & containment решения — за да изградим дата-центрове, подготвени за бъдещите изисквания.

• Надеждност:
Всеки детайл е изграден и тестван с прецизност — сертифицирани стандарти, документи, тестове. Гарантираме стабилност, безопасност и непрекъснато функциониране дори при тежки натоварвания.

• Партньорство:
Работим в тясно сътрудничество с клиентите — открита комуникация, професионално изпълнение и споделена отговорност. Вашият успех е наша задача.

• Качество и съответствие:
Спазваме международни стандарти (Tier III / Tier IV), провеждаме строг тестинг, документация и спазване на безопасност и проследимост. Без компромиси.

Контакти и подкрепа
Ако планирате нов build, ъпгрейд, миграция или оптимизация на дата-център — нашият екип е готов да помогне. Работим в цяла Европа и предоставяме инфраструктура, съобразена с вашите натоварвания, планове за растеж и изисквания за надеждност.
"""

# =========================
# Бизнес конфигурация
# =========================

BUSINESSES = {
    "vlt_data": {
        "name": "VLT DATA SOLUTIONS",
        "languages": ["bg", "en"],
        "description_en": BUSINESS_DESCRIPTION_EN,
        "description_bg": BUSINESS_DESCRIPTION_BG,
        "tone_bg": "Професионален, спокоен, технически, но разбираем.",
        "tone_en": "Professional, calm and technical, but clear for non-technical people.",
        # Примерен search шаблон (ако сайтът има search параметър ?s= )
        "search_url_template": "https://vltdatasolutions.com/?s={query}"
    }
    # по-късно тук добавяме и магазини (гуми, техника и т.н.) с техните шаблони
}

APPOINTMENT_MARKER = "##APPOINTMENT##"
SEARCH_MARKER = "##SEARCH_LINK##"
CONTACT_MARKER = "##CONTACT_MESSAGE##"


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

APPOINTMENTS / LEADS (PROJECTS, OFFERS):
- If the user is clearly interested in a project, offer, quotation, on-site work, data center build,
  upgrade, migration or maintenance, you should gently collect contact details.

- Ask naturally (not as a rigid form) for:
  * full name
  * company (if any)
  * email
  * phone (if possible)
  * country/city or site location
  * short description of the project (scope, timelines, criticality)

- Always keep track of what information you already have.
  If some details are missing, ASK ONLY FOR THE MISSING FIELDS, not for everything again.

- As soon as you have AT LEAST:
  * name
  * at least one contact (email OR phone)
  * a short project description

  you MUST:
  1) stop asking for more details,
  2) thank the user and confirm that the {biz['name']} team will contact them,
  3) append at the very end of your answer a single line in the following format:

  {APPOINTMENT_MARKER} {{
    "name": "...",
    "company": "...",
    "email": "...",
    "phone": "...",
    "location": "...",
    "project_description": "...",
    "preferred_contact": "...",
    "language": "bg or en"
  }}

- The JSON must be valid and on a single line. Keys are ALWAYS in English.
- Do NOT explain this JSON to the user and do NOT mention that you are creating an appointment.
- In your visible answer, just confirm that the {biz['name']} team will contact them and optionally
  summarise the key project details you understood.

WEBSITE & LINK SEARCH (SEARCH_LINK):
- Sometimes the user will look for something that can be answered best with a direct link
  to a relevant page or search results on the website. Examples:
  - "Покажи ми повече за data center услугите"
  - "Искам да видя страница с проекти"
  - For shops (in other businesses): "търся гуми 205/55 R16 Michelin", "търся пералня 8 кг Bosch"

- When such intent is clear, you may both:
  1) give a short helpful explanation,
  2) and at the END of your answer add a single line in the format:

  {SEARCH_MARKER} {{
    "query": "user search text or extracted keywords",
    "category": "optional category such as 'tires', 'electronics', 'services'"
  }}

- Do NOT put URLs directly inside this JSON. The backend will map this to a concrete URL
  using the business configuration.
- The JSON must be on a single line and valid.

CONTACT MESSAGES TO THE COMPANY (CONTACT_MESSAGE):
- If the user explicitly says that they want to send a message to the company, for example:
  - "Имам запитване"
  - "Искам да изпратя съобщение към фирмата"
  - "Може ли да пратя имейл до вас през чата?"

  then you should:
  - Explain briefly that you can collect their message and forward it to the team.
  - Ask for:
    * name
    * email
    * phone (optional but recommended)
    * subject (short title)
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

TASK:
- Answer only about data center infrastructure, services and capabilities of {biz['name']}.
- If the user asks something unrelated (weather, politics, random topics),
  politely explain that your role is to assist only with the services and expertise of {biz['name']}.
- For contact or projects, encourage the user to briefly describe their project
  (new data center, upgrade, migration, maintenance) and then collect the data as explained above.
"""


# =========================
# FastAPI приложение
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # по-късно може да го стесним към конкретни домейни
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
    return {"status": "ok", "service": "chatvlt", "businesses": list(BUSINESSES.keys())}


# =========================
# Helpers за записи
# =========================

def save_appointment(business_id: str, json_str: str) -> None:
    """
    Опитва да parse-не JSON-а след APPOINTMENT маркера и да го запише във файл appointments.log
    """
    try:
        m = re.search(r"\{.*\}", json_str, re.DOTALL)
        if not m:
            return
        data = json.loads(m.group(0))

        record = {
            "business_id": business_id,
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            **data,
        }

        with open("appointments.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def save_contact_message(business_id: str, json_str: str) -> None:
    """
    Записва контактно съобщение във файл contact_messages.log.
    По-късно тук може да добавим реално изпращане на имейл.
    """
    try:
        m = re.search(r"\{.*\}", json_str, re.DOTALL)
        if not m:
            return
        data = json.loads(m.group(0))

        record = {
            "business_id": business_id,
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            **data,
        }

        with open("contact_messages.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Тук по-късно може да добавим SMTP / имейл интеграция
        # напр. използвайки os.getenv("CONTACT_EMAIL_TO") и т.н.

    except Exception:
        pass


def build_search_url(business_id: str, json_str: str) -> Optional[str]:
    """
    На база на SEARCH_LINK JSON-а + конфигурацията на бизнеса
    връща конкретен URL към сайта (търсене/страница).
    """
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

    except Exception:
        return None


# =========================
# Основен /chat endpoint
# =========================

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message.")

    business_id = req.business_id or "vlt_data"
    system_prompt = build_system_prompt(business_id)

    # История на разговора
    messages = [{"role": "system", "content": system_prompt}]

    if req.history:
        for m in req.history[-10:]:
            role = m.get("role")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": req.message})

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=700,
        )

        raw_reply = completion.choices[0].message.content.strip()
        visible_reply = raw_reply

        # 1) обработваме APPOINTMENT
        if APPOINTMENT_MARKER in visible_reply:
            before, after = visible_reply.split(APPOINTMENT_MARKER, 1)
            visible_reply = before.strip()
            save_appointment(business_id, after.strip())

        # 2) обработваме CONTACT_MESSAGE
        if CONTACT_MARKER in visible_reply:
            before, after = visible_reply.split(CONTACT_MARKER, 1)
            visible_reply = before.strip()
            save_contact_message(business_id, after.strip())

        # 3) обработваме SEARCH_LINK
        if SEARCH_MARKER in visible_reply:
            before, after = visible_reply.split(SEARCH_MARKER, 1)
            visible_reply = before.strip()
            url = build_search_url(business_id, after.strip())
            if url:
                # добавяме линка в края на отговора
                visible_reply = f"{visible_reply}\n\n👉 Линк: {url}"

        return ChatResponse(reply=visible_reply)

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Error while generating response from ChatVLT.",
        )
