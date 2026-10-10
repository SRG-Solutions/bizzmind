"""UI language plumbing: LANGS, server-side message catalogue and T()."""

from fastapi import Request


# ---------------------------------------------------------------- i18n
# The UI language travels in the `lang` cookie (set by static/i18n/core.js).
# Server-side texts (errors, activity feed, PDF labels) go through T();
# AI prompts get the language name so every generated label matches the UI.
LANGS = ("bg", "en")
LANG_NAMES = {"bg": "Bulgarian", "en": "English"}
MSG: dict = {
    "bg": {
        "app_form_invalid": "Формата не се зареди. Обнови приложението и опитай отново.",
        "app_record_invalid": "Промяната не е запазена. Провери стойностите и задължителните полета.",
        "app_record_conflict": "Записът е променен след отварянето му. Избери го отново и повтори промяната.",
        "password_short": "Паролата трябва да е поне 8 символа.",
        "email_taken": "Вече има акаунт с този имейл.",
        "confirm_email": "Изпратихме линк за потвърждение на имейла ти. Потвърди го и влез.",
        "forbidden": "Нямаш достъп до този проект.",
        "pres_no_credits": "Кредитите за презентации на организацията са изчерпани. Свържи се с нас, за да добавим още.",
        "no_credits": "Кредитите на организацията са изчерпани — добави още от Акаунт → Кредити.",
        "no_credits_need": "Нужни са {need} кредита, а имаш {have}. Купи кредити или премини на по-висок план.",
        "model_not_in_plan": "Моделът Max е достъпен от план Pro нагоре.",
        "plan_projects_limit": "Планът {plan} позволява до {n} проект(а). Премини на по-висок план за повече.",
        "plan_files_limit": "Планът {plan} позволява до {n} файла на проект.",
        "plan_file_too_big": "„{name}“ е {mb} MB — планът {plan} позволява до {max} MB на файл.",
        "act_sql_purpose": "🔍 {what}",
        "act_app_updated": "🧩 Промених приложението: {what}",
        "act_app_thinking": "🧩 Разглеждам данните и мисля какво приложение би помогнало…",
        "act_app_designing": "🧩 Проектирам приложението от данните…",
        "act_app_ready": "🧩 Приложението е готово",
        "err_app_invalid": "AI-ят не върна валидна спецификация за приложението.",
        "act_translating": "🌐 Превеждам съдържанието на дашборда ({n} текста)…",
        "act_translated": "🌐 Преведох {n} текста",
        # auth / projects
        "not_logged_in": "Не си влязъл — влез отново.",
        "bad_credentials": "Грешен имейл или парола.",
        "new_project": "Нов проект",
        # activity feed (agent tool callbacks)
        "act_verify": "🧪 Проверка на дашборда: {status}",
        "act_verify_ok": "✅ всичко работи",
        "act_verify_err": "⚠️ има грешки — поправям",
        "act_turn_limit": "⏹ Спрях след твърде много опити — виж какво е останало недовършено.",
        "act_verify_giveup": "⏹ Няколко поправки поред не помогнаха — спирам и описвам какво остава.",
        "act_sql_retry": "🔁 Коригирам заявката (пробвам друг подход)…",
        "act_tool_error": "⚠️ {name}: {detail}",
        "act_sql_look": "🔍 Разглеждам: {sql}",
        "act_note": "💾 Запомних: {note}",
        "act_filter": "🎛 Филтър „{label}“",
        "act_view": "🧩 Изглед „{name}“ — {desc}",
        "act_view_drop": "🧩 Премахнах изглед „{name}“",
        "act_chart": "📊 Графика „{title}“",
        "act_chart_upd": "✏️ Обнових графика „{title}“",
        "act_chart_del": "🗑 Премахнах графика #{id}",
        "act_questions": "❓ Подготвям {n} въпроса с предложения",
        "act_new_session": "🔌 Нова AI сесия",
        "act_session_recap": " — продължавам разговора от резюме",
        "act_thinking": "🧠 Мисля — чета контекста и планирам стъпките…",
        "act_table_loaded": "📥 Таблица „{table}“ — {rows} реда, {cols} колони",
        "act_edit": "✏️ Редакция: {table}.{column} → {value}",
        "act_brand_extracted": "🎨 Извлякох {colors} цвята и {fonts} шрифта от книгата",
        "act_brand_file": "🎨 Бранд файл „{name}“",
        "act_deck_writing": "📽 Пиша съдържанието на презентацията…",
        "act_pdf": "📄 PDF отчет ({n} графики)",
        # chat transcript events
        "chat_files_loaded": "Качени файлове → таблици: {tables}",
        "chat_context": "Какво знам за данните: {text}",
        "chat_goal": "Какво искам да постигна: {text}",
        "chat_deck_ready": "Подготвих съдържанието и брифа на презентацията.",
        # errors (HTTP details)
        "err_no_table": "Няма таблица '{table}'.",
        "err_no_column": "Няма колона '{column}'.",
        "err_not_number": "'{value}' не е число, а колоната е числова.",
        "err_brand_ext": "'{name}': за бранд приемам PDF, PNG, JPG или SVG.",
        "err_brand_missing": "Няма такъв бранд файл.",
        "err_deck_no_charts": "Няма графики, от които да направя презентация.",
        "err_deck_invalid": "AI не върна валидна презентация — опитай пак.",
        "err_deck_json": "AI върна невалиден JSON за презентацията — опитай пак.",
        "err_ai_offline": "В момента не мога да стигна до AI помощника. Задачата е "
                          "спряна и нищо не ти е таксувано — опитай пак след малко. "
                          "Ако продължава, пиши ни.",
        "err_ai_timeout": "AI отговаря прекалено дълго и заявката беше прекъсната. "
                          "Опитай пак — при много файлове първият преглед може да е бавен.",
        "err_ai_failed": "AI заявката се провали: {detail}",
        "err_ai_unreachable": "Няма връзка с AI услугата. Провери мрежата.",
        "err_ai_sub_failed": "AI заявката (абонамент) се провали: {detail}",
        "err_ai_refusal": "Съжалявам — не мога да помогна с това. Попитай нещо за данните си.",
        "err_gamma_not_configured": "Gamma не е настроена — липсва GAMMA_API_KEY в .env",
        "err_gamma_status": "Gamma отговори {code}: {detail}",
        "err_gamma_unreachable": "Gamma недостъпна — {detail}",
        # deck / PDF / Gamma content
        "deck_no_brand": "няма качен бранд бук",
        "pdf_report": "Аналитичен отчет",
        "pdf_page": "стр. {n}",
        "pdf_filters": "Филтри: {text}",
        "date_fmt": "%d.%m.%Y",
        "gamma_takeaways": "Изводи и препоръки",
        "gamma_warn_images": "{n} графики не са вградени — сървърът няма публичен адрес "
                             "(PUBLIC_BASE_URL). Gamma получава данните им като таблици.",
        "g_preserve": "Запази текста", "g_preserve_hint": "Точно нашите заглавия и изводи",
        "g_condense": "Сбито", "g_condense_hint": "Gamma съкращава до същественото",
        "g_generate": "Разгърни", "g_generate_hint": "Gamma дописва и разширява",
        "g_img_none": "Само нашите графики", "g_img_theme": "Акценти от темата",
        "g_img_ai": "AI илюстрации", "g_img_picto": "Пиктограми", "g_img_stock": "Стокови снимки",
        "lang_bg": "Български", "lang_en": "English",
    },
    "en": {
        "act_app_updated": "🧩 Updated the app: {what}",
        "app_form_invalid": "This form could not be loaded. Refresh the app and try again.",
        "app_record_invalid": "Changes were not saved. Check the values and required fields.",
        "app_record_conflict": "This record changed after you opened it. Select it again and reapply your changes.",
        "password_short": "The password must be at least 8 characters.",
        "email_taken": "An account with this email already exists.",
        "confirm_email": "We sent a confirmation link to your email. Confirm it, then sign in.",
        "forbidden": "You do not have access to this project.",
        "pres_no_credits": "Your organisation has run out of presentation credits. Contact us to top up.",
        "no_credits": "Your organisation is out of credits — top up from Account → Credits.",
        "no_credits_need": "This needs {need} credits and you have {have}. Buy credits or upgrade your plan.",
        "model_not_in_plan": "The Max model is available from the Pro plan up.",
        "plan_projects_limit": "The {plan} plan allows up to {n} project(s). Upgrade for more.",
        "plan_files_limit": "The {plan} plan allows up to {n} files per project.",
        "plan_file_too_big": "\u201c{name}\u201d is {mb} MB — the {plan} plan allows up to {max} MB per file.",
        "act_translating": "🌐 Translating the dashboard content ({n} texts)…",
        "act_translated": "🌐 Translated {n} texts",
        # auth / projects
        "not_logged_in": "You are not signed in — please sign in again.",
        "bad_credentials": "Incorrect email or password.",
        "new_project": "New project",
        # activity feed (agent tool callbacks)
        "act_verify": "🧪 Dashboard check: {status}",
        "act_verify_ok": "✅ everything works",
        "act_verify_err": "⚠️ found issues — fixing them",
        "act_turn_limit": "⏹ Stopped after too many attempts — see what is left unfinished.",
        "act_verify_giveup": "⏹ Several repairs in a row did not help — stopping and describing what remains.",
        "act_sql_retry": "🔁 Adjusting the query (trying another approach)…",
        "act_tool_error": "⚠️ {name}: {detail}",
        "act_sql_look": "🔍 Looking at: {sql}",
        "act_note": "💾 Noted: {note}",
        "act_filter": "🎛 Filter “{label}”",
        "act_view": "🧩 View “{name}” — {desc}",
        "act_view_drop": "🧩 Removed view “{name}”",
        "act_chart": "📊 Chart “{title}”",
        "act_chart_upd": "✏️ Updated chart “{title}”",
        "act_chart_del": "🗑 Removed chart #{id}",
        "act_questions": "❓ Preparing {n} questions with suggestions",
        "act_new_session": "🔌 New AI session",
        "act_session_recap": " — continuing the conversation from a summary",
        "act_thinking": "🧠 Thinking — reading the context and planning the steps…",
        "act_table_loaded": "📥 Table “{table}” — {rows} rows, {cols} columns",
        "act_edit": "✏️ Edit: {table}.{column} → {value}",
        "act_brand_extracted": "🎨 Extracted {colors} colours and {fonts} fonts from the brand book",
        "act_brand_file": "🎨 Brand file “{name}”",
        "act_deck_writing": "📽 Writing the presentation content…",
        "act_pdf": "📄 PDF report ({n} charts)",
        # chat transcript events
        "chat_files_loaded": "Uploaded files → tables: {tables}",
        "chat_context": "What I know about the data: {text}",
        "chat_goal": "What I want to achieve: {text}",
        "chat_deck_ready": "The presentation content and design brief are ready.",
        # errors (HTTP details)
        "err_no_table": "There is no table '{table}'.",
        "err_no_column": "There is no column '{column}'.",
        "err_not_number": "'{value}' is not a number, but the column is numeric.",
        "err_brand_ext": "'{name}': brand files must be PDF, PNG, JPG or SVG.",
        "err_brand_missing": "No such brand file.",
        "err_deck_no_charts": "There are no charts to build a presentation from.",
        "err_deck_invalid": "The AI did not return a valid presentation — please try again.",
        "err_deck_json": "The AI returned invalid JSON for the presentation — please try again.",
        "err_ai_offline": "I can't reach the AI assistant right now. The task was "
                          "stopped and you were not charged — please try again in a "
                          "moment. If it keeps happening, get in touch.",
        "err_ai_timeout": "The AI took too long and the request was cancelled. "
                          "Try again — with many files the first review can be slow.",
        "err_ai_failed": "AI request failed: {detail}",
        "err_ai_unreachable": "Could not reach the AI service. Check your network.",
        "err_ai_sub_failed": "Subscription AI request failed: {detail}",
        "err_ai_refusal": "Sorry — I can't help with that request. Try asking about your data.",
        "err_gamma_not_configured": "Gamma is not configured — GAMMA_API_KEY is missing in .env",
        "err_gamma_status": "Gamma responded {code}: {detail}",
        "err_gamma_unreachable": "Gamma is unreachable — {detail}",
        # deck / PDF / Gamma content
        "deck_no_brand": "no brand book uploaded",
        "pdf_report": "Analytics report",
        "pdf_page": "p. {n}",
        "pdf_filters": "Filters: {text}",
        "date_fmt": "%d %b %Y",
        "gamma_takeaways": "Key takeaways and recommendations",
        "gamma_warn_images": "{n} charts were not embedded — the server has no public address "
                             "(PUBLIC_BASE_URL). Gamma receives their data as tables instead.",
        "g_preserve": "Keep the text", "g_preserve_hint": "Exactly our headlines and takeaways",
        "g_condense": "Condense", "g_condense_hint": "Gamma trims to the essentials",
        "g_generate": "Expand", "g_generate_hint": "Gamma elaborates and extends",
        "g_img_none": "Only our charts", "g_img_theme": "Theme accents",
        "g_img_ai": "AI illustrations", "g_img_picto": "Pictograms", "g_img_stock": "Stock photos",
        "lang_bg": "Български", "lang_en": "English",
    },
}


def req_lang(request: Request | None) -> str:
    try:
        l = request.cookies.get("lang", "") if request is not None else ""
    except Exception:
        l = ""
    return l if l in LANGS else "bg"


def T(lang: str, key: str, **kw) -> str:
    s = MSG.get(lang, {}).get(key)
    if s is None:
        s = MSG["bg"].get(key, key)
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError):
        return s
