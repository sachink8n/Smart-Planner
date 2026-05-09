import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def call_groq_api(prompt, max_completion_tokens=1024, temperature=0.2):
    API_KEY = os.environ.get("GROQ_API_KEY")

    if not API_KEY:
        print("ERROR: GROQ_API_KEY not set.")
        return ""
        
    try:
        client = Groq(api_key=API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API Error: {e}")
        return ""


def get_task_category_with_ai(sentence):
    """
    Uses the Groq API to determine the category of a task.
    """
    categories = "Work, Personal, Learning, Health, Shopping, Other"
    prompt = f"Classify the following task into one single category: [{categories}]. Return ONLY the single best category name. Task: '{sentence}'"
    raw_output = call_groq_api(prompt)
    print(f"AI Raw Output (Category): {raw_output}")
    for category in categories.split(', '):
        if re.search(r'\b' + re.escape(category) + r'\b', raw_output, re.IGNORECASE):
            return category
    return "Other"


def get_task_difficulty_with_ai(sentence):
    """AI se task ki difficulty pata karta hai."""
    difficulties = "Easy, Moderate, Hard"
    prompt = f"Classify this task's difficulty: [{difficulties}]. Return ONLY the single best difficulty level. Task: '{sentence}'"
    raw_output = call_groq_api(prompt)
    print(f"AI Raw Output (Difficulty): {raw_output}")
    for difficulty in difficulties.split(', '):
        if re.search(r'\b' + re.escape(difficulty) + r'\b', raw_output, re.IGNORECASE):
            return difficulty
    return "Moderate"


def get_time_estimate_with_ai(sentence, difficulty):
    """AI se task ka time estimate (minutes me) pata karta hai."""
    prompt = f"Estimate the time in minutes to complete this task. The task is '{sentence}' and its difficulty is '{difficulty}'. Return ONLY a single number (e.g., '45')."
    raw_output = call_groq_api(prompt)
    print(f"AI Raw Output (Time): {raw_output}")
    numbers = re.findall(r'\d+', raw_output)
    if numbers:
        return int(numbers[0])
    return 25 


def get_sub_tasks_with_ai(sentence):
    """
    Uses Groq API to generate detailed, premium sub-tasks with HTML formatting.
    """
    prompt = f"""
    You are an expert productivity coach. A user wants to tackle a big task. 
    Task: "{sentence}"

    Return a structured guide with these sections in this exact order:
    1. Prerequisites: 2-4 bullets about what should be ready before starting.
    2. Step-by-step path: 3-5 bullets with clear action verbs.
    3. Keep each bullet short, practical, and beginner-friendly.
    4. Use a plain text outline with section headings and bullet points.

    Return ONLY the outline. Do not add any intro or conclusion.

    EXAMPLE:
    USER GOAL: "Learn Django REST Framework"
    YOUR OUTPUT:
    Prerequisites:
    - Python installed
    - Django project set up
    - Basic REST concepts understood

    Step-by-step path:
    - Review serializers and views
    - Set up the app and install dependencies
    - Build a simple read-only API
    - Test the endpoint
    - Add permissions
    """
    
    raw_output = call_groq_api(prompt + f'\nNOW, DO THE SAME FOR THIS TASK: "{sentence}"\nYOUR OUTPUT:')
    print(f"AI Raw Output (Expert Sub-tasks): {raw_output}")

    sub_tasks = []
    seen_lines = set()

    def add_line(line):
        normalized = line.strip()
        if normalized and normalized not in seen_lines:
            sub_tasks.append(normalized)
            seen_lines.add(normalized)

    def normalize_heading(line):
        normalized = re.sub(r'^#+\s*', '', line).strip()
        normalized = re.sub(r'\s*:\s*$', '', normalized)
        lowered = normalized.lower()
        if lowered in {'prerequisites', 'prerequisite'}:
            return 'Prerequisites:'
        if lowered in {'step-by-step path', 'step by step path', 'steps', 'execution steps'}:
            return 'Step-by-step path:'
        return f"{normalized}:" if normalized else ''

    for line in raw_output.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue

        if re.match(r'^(#{1,6}\s*)?(prerequisites?|step[- ]?by[- ]step path|steps?|execution steps?)\s*:?$', clean_line, re.IGNORECASE):
            add_line(normalize_heading(clean_line))
            continue

        if clean_line.startswith(('-', '*')) or re.match(r'^\d+[\.)]\s*', clean_line):
            processed_line = re.sub(r'^[\-\*\d\.)\s]+', '', clean_line).strip()
            add_line(f"- {processed_line}")
    
    if not sub_tasks and raw_output:
        return raw_output.strip()
        
    return "\n".join(sub_tasks)


def _fallback_quiz_questions(title, summary_text, difficulty):
    clean_summary = summary_text.strip()[:300] if summary_text else ""
    topic_hint = title.strip() if title else "the topic"
    topic_focus = topic_hint.lower()
    return [
        {
            "question": f"What is the main idea behind {topic_hint}?",
            "options": [
                f"The concept described by {topic_focus}",
                "A random productivity habit",
                "An unrelated scheduling method",
                "A completely different subject",
            ],
            "answer": f"The concept described by {topic_focus}",
            "explanation": "The quiz should stay anchored to the topic named in the task.",
        },
        {
            "question": f"Which option is most closely related to {topic_hint}?",
            "options": [
                f"A key idea connected to {topic_focus}",
                "A preparation tip for a generic chore",
                "A random motivational quote",
                "An unrelated time-management trick",
            ],
            "answer": f"A key idea connected to {topic_focus}",
            "explanation": "The question should test the subject matter, not the workflow.",
        },
        {
            "question": f"Which statement best matches the topic of {topic_hint}?",
            "options": [
                f"It describes an important concept in {topic_focus}",
                "It describes an unrelated reminder",
                "It is about finishing a checklist",
                "It is about ignoring the topic",
            ],
            "answer": f"It describes an important concept in {topic_focus}",
            "explanation": "Use the topic itself as the basis for the quiz.",
        },
        {
            "question": f"What kind of knowledge should this quiz check for {topic_hint}?",
            "options": [
                "Understanding of the topic",
                "How quickly you can submit",
                "Whether you copied the title",
                "Whether you skipped the task",
            ],
            "answer": "Understanding of the topic",
            "explanation": "The quiz should measure subject knowledge, not task-management steps.",
        },
        {
            "question": f"Which summary best describes {topic_hint}? {clean_summary[:80] if clean_summary else ''}",
            "options": [
                "It matches the topic and the main idea",
                "It talks about a random unrelated subject",
                "It avoids the topic entirely",
                "It only checks formatting",
            ],
            "answer": "It matches the topic and the main idea",
            "explanation": "The fallback quiz should remain topic-focused.",
        },
    ]


_QUIZ_GENERIC_PATTERNS = (
    "what should you do first",
    "before starting",
    "most productive next step",
    "follow the step-by-step path",
    "recommended difficulty",
    "task context",
    "main goal of",
    "prepare",
    "prerequisite",
)


def _quiz_question_is_topic_focused(question, title):
    question_text = re.sub(r'\s+', ' ', str(question or '').strip().lower())
    title_text = re.sub(r'\s+', ' ', str(title or '').strip().lower())

    if not question_text:
        return False

    if any(pattern in question_text for pattern in _QUIZ_GENERIC_PATTERNS):
        return False

    title_tokens = [token for token in re.findall(r'[a-z0-9]+', title_text) if len(token) > 2]
    if not title_tokens:
        return True

    return any(token in question_text for token in title_tokens[:3])


def generate_task_quiz_with_ai(title, summary_text='', difficulty='Moderate', question_count=5):
    """
    Creates 5-7 MCQ questions for a completed task.
    """
    question_count = max(5, min(int(question_count or 5), 7))
    prompt = f"""
You are an expert tutor creating a topic-focused quiz.

Task title / topic: {title}
Difficulty: {difficulty}
Task summary / steps:
{summary_text or 'No extra summary available.'}

Generate exactly {question_count} multiple-choice questions.
Rules:
1. Return ONLY valid JSON.
2. Output must be a JSON array.
3. Each item must have keys: question, options, answer, explanation.
4. options must be an array of exactly 4 strings.
5. answer must match one of the options exactly.
6. Every question must be about the actual topic in the title, not about generic task completion.
7. Avoid generic workflow questions such as first step, preparation, step order, or productivity habits unless they are explicitly part of the topic.
8. Prefer definitions, causes, examples, comparisons, and applications related to the topic.
9. Keep language simple and clear.
"""

    raw_output = call_groq_api(prompt, max_completion_tokens=1800, temperature=0.2)
    if raw_output:
        try:
            parsed = json.loads(raw_output)
            if isinstance(parsed, list) and parsed:
                cleaned = []
                for item in parsed[:question_count]:
                    if not isinstance(item, dict):
                        continue
                    options = item.get('options') or []
                    answer = item.get('answer') or ''
                    question = (item.get('question') or '').strip()
                    explanation = (item.get('explanation') or '').strip()
                    if question and isinstance(options, list) and len(options) == 4 and answer in options and _quiz_question_is_topic_focused(question, title):
                        cleaned.append({
                            'question': question,
                            'options': [str(option).strip() for option in options],
                            'answer': str(answer).strip(),
                            'explanation': explanation,
                        })
                if len(cleaned) >= question_count:
                    return cleaned[:question_count]
        except Exception:
            pass

    return _fallback_quiz_questions(title, summary_text, difficulty)[:question_count]


def generate_study_plan_with_ai(subject, goal, duration_days):
    """
    Generates a detailed, day-by-day plan with HTML formatting.
    """

    def _fallback_day_block(day_number):
        return (
            f"## Day {day_number}: Focused Progress\n"
            f"- <strong style=\"color: var(--accent-color);\">Review previous learning</strong>: Revise key concepts from earlier days and note weak points related to <em style=\"color: #bdbdbd; font-style: italic;\">{subject}</em>.\n"
            f"- <strong style=\"color: var(--accent-color);\">Deep study session</strong>: Work on one concrete milestone connected to your goal: <em style=\"color: #bdbdbd; font-style: italic;\">{goal}</em>.\n"
            f"- <strong style=\"color: var(--accent-color);\">Hands-on practice</strong>: Build or solve a practical exercise and record errors, fixes, and outcomes.\n"
            f"- <strong style=\"color: var(--accent-color);\">Reflection and planning</strong>: Summarize what you learned and prepare the next day action list."
        )

    def _generate_chunk(start_day, end_day):
        prompt = f"""
You are an expert academic advisor creating a high-quality study plan.
Subject: "{subject}"
Goal: "{goal}"
Overall duration: {duration_days} days.

Generate ONLY Day {start_day} to Day {end_day}.

Hard constraints:
1. Include EVERY day from {start_day} to {end_day} exactly once.
2. Use this heading format exactly: ## Day N: [Meaningful Title]
3. For each day, include at least 4 bullet tasks starting with "- ".
4. Keep tasks actionable and specific.
5. Output only the plan text for these days.
"""
        return call_groq_api(prompt, max_completion_tokens=3500, temperature=0.2)

    chunks = []
    chunk_size = 5
    for start_day in range(1, duration_days + 1, chunk_size):
        end_day = min(start_day + chunk_size - 1, duration_days)
        chunk_text = _generate_chunk(start_day, end_day)
        print(f"AI Raw Output (Plan Chunk {start_day}-{end_day}): {chunk_text}")
        if not chunk_text:
            chunk_text = "\n\n".join(_fallback_day_block(day_no) for day_no in range(start_day, end_day + 1))
        chunks.append(chunk_text)

    plan_text = "\n\n".join(chunks)

    found_days = {int(day) for day in re.findall(r'##\s*Day\s*(\d+)\s*:', plan_text, flags=re.IGNORECASE)}
    missing_days = [day for day in range(1, duration_days + 1) if day not in found_days]
    if missing_days:
        plan_text += "\n\n" + "\n\n".join(_fallback_day_block(day_no) for day_no in missing_days)

    processed_text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: var(--accent-color);">\1</strong>', plan_text)
    processed_text = re.sub(r'[\*\_]([^\*\_]+)[\*\_]', r'<em style="color: #bdbdbd; font-style: italic;">\1</em>', processed_text)

    return processed_text if processed_text else "Could not generate a plan."