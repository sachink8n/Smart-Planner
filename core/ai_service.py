# core/ai_service.py
import os
import re
from groq import Groq


def call_groq_api(prompt):
    API_KEY = os.environ.get("GROQ_API_KEY")
    if not API_KEY:
        print("ERROR: GROQ_API_KEY not set.")
        return ""
    try:
        client = Groq(api_key=API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant", 
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
    
    prompt = f"""
    You are an expert academic advisor creating a highly detailed study plan.
    Student's Subject: "{subject}"
    Student's Goal: "{goal}"
    Total Duration: {duration_days} days.

    Create a realistic, day-by-day plan.
    
    **CRITICAL INSTRUCTIONS:**
    1.  For EACH day, provide a clear, meaningful title.
    2.  For EACH day, provide a list of **at least 4-5 highly detailed** tasks.
    3.  **DO NOT** just list topics. For each task, explain *how* to do it, *what* to focus on, or provide specific examples (e.g., "Watch a video on..." or "Implement a function that..."). The user wants to know the *process* of achieving the task.

    **CRITICAL FORMATTING RULES:**
    1.  Start each day with: `## Day 1: [Meaningful Day Title]`
    2.  Start each task with a bullet point (`- `).
    3.  Wrap the main action/concept in HTML: `<strong style="color: var(--accent-color);">...</strong>`.
    4.  Wrap any specific tools, terms, or examples in HTML: `<em style="color: #bdbdbd; font-style: italic;">...</em>`.

    **EXAMPLE OUTPUT:**
    ## Day 1: Introduction to Node.js
    - <strong style="color: var(--accent-color);">Set Up Environment</strong>: Install the latest LTS version of <em style="color: #bdbdbd; font-style: italic;">Node.js</em> from the official website. Verify the installation in your terminal using `node -v` and `npm -v`.
    - <strong style="color: var(--accent-color);">Understand Core Modules</strong>: Read about the <em style="color: #bdbdbd; font-style: italic;">fs</em> (File System) module for reading/writing files and the <em style="color: #bdbdbd; font-style: italic;">http</em> module for creating a basic server.
    - <strong style="color: var(--accent-color);">Create First Server</strong>: Write a simple 'server.js' file that uses the <em style="color: #bdbdbd; font-style: italic;">http</em> module to create a server that responds with 'Hello, World!' on port 3000.
    - <strong style="color: var(--accent-color);">Learn NPM Basics</strong>: Initialize a new project using `npm init -y`. Learn how to install external packages, like <em style="color: #bdbdbd; font-style: italic;">nodemon</em>, to automatically restart your server on file changes.

    Return ONLY the plan. Do not add any introductory or concluding text.
    """
    
    plan_text = call_groq_api(prompt + f'\nNOW, DO THE SAME FOR: "{subject}" with the goal "{goal}"\nYOUR OUTPUT:')
    print(f"AI Raw Output (Plan): {plan_text}")

   
    processed_text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: var(--accent-color);">\1</strong>', plan_text)
    processed_text = re.sub(r'[\*\_]([^\*\_]+)[\*\_]', r'<em style="color: #bdbdbd; font-style: italic;">\1</em>', processed_text)

    return processed_text if processed_text else "Could not generate a plan."