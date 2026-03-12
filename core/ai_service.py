import os
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

    Break this task down into 3-5 highly detailed and actionable sub-tasks. 
    For each sub-task:
    1.  Start with a clear action verb.
    2.  Briefly explain *why* this step is important or *how* to approach it.
    3.  Use markdown **bold** for the main action/concept.
    4.  Use markdown *italics* for any specific tools or key terms.

    Return ONLY the bulleted list. Do not add any intro or conclusion.

    EXAMPLE:
    USER GOAL: "Learn Django REST Framework"
    YOUR OUTPUT:
    - **Research** core concepts: Start by understanding *serializers* (how data is converted), *viewssets* (how logic is handled), and *routers* (how URLs are created).
    - **Set up** a basic project: Install *djangorestframework* and add it to `INSTALLED_APPS` in your settings.py file to create the foundation.
    - **Build** a simple "read-only" API: Create a 'Book' model and a 'BookSerializer' to see how your model's data is converted to JSON.
    - **Test** the API: Use *Postman* or your browser to make a GET request to your new endpoint and see the live JSON data.
    - **Implement** basic permissions: Add `IsAuthenticated` to your view to understand how to protect your API.
    """
    
    raw_output = call_groq_api(prompt + f'\nNOW, DO THE SAME FOR THIS TASK: "{sentence}"\nYOUR OUTPUT:')
    print(f"AI Raw Output (Expert Sub-tasks): {raw_output}")

    sub_tasks = []
    for line in raw_output.splitlines():
        if line.strip().startswith(('-', '*')) or re.match(r'^\d+\.', line.strip()):
            processed_line = line.strip("-* ").strip()
            # **Bold** to <strong style="color: var(--accent-color);">...</strong>
            processed_line = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: var(--accent-color);">\1</strong>', processed_line)
            # *Italic* or _Italic_ to <em style="color: #bdbdbd; font-style: italic;">...</em>
            processed_line = re.sub(r'[\*\_]([^\*\_]+)[\*\_]', r'<em style="color: #bdbdbd; font-style: italic;">\1</em>', processed_line)
            sub_tasks.append(processed_line)
    
    if not sub_tasks and raw_output:
        return [raw_output.strip()]
        
    return sub_tasks


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