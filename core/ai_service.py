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
    You are an expert productivity coach. A user wants a compact learning roadmap for a technical topic.
    Task: "{sentence}"

    Output EXACTLY this plain-text structure (no extra commentary):

    Prerequisites:
    - <concise semicolon-separated list of 2-4 prerequisite items>

    Step-by-step path:
    - Step 1: <short title> — <1-2 sentence actionable instruction>
    - Step 2: <short title> — <1-2 sentence actionable instruction>
    - Step 3: <short title> — <1-2 sentence actionable instruction>
    - Step 4: <short title> — <1-2 sentence actionable instruction>
    (Create 4 or 5 Step lines total.)

    Keep language practical and specific. Use hyphen bullets and include numeric step titles.
    Return ONLY the outline text; do not add headings, explanations, or extra lines outside the shown structure.
    """

    raw_output = call_groq_api(prompt + f"\nNOW, DO THE SAME FOR THIS TASK: \"{sentence}\"\nYOUR OUTPUT:")
    print(f"AI Raw Output (Expert Sub-tasks): {raw_output}")

    # Parse and coalesce prerequisites into a single bullet; keep numbered step bullets separate.
    prereq_items = []
    step_lines = []
    mode = None

    for line in (raw_output or '').splitlines():
        raw = line.strip()
        if not raw:
            continue

        # handle inline 'Prerequisites: item1, item2' on single line
        m_inline_pr = re.match(r'^\s*prerequisites\s*:\s*(.+)$', raw, re.IGNORECASE)
        if m_inline_pr:
            items = re.split(r'[;,]\s*|\s+and\s+', m_inline_pr.group(1))
            for it in items:
                it = it.strip()
                if it:
                    prereq_items.append(it)
            mode = 'prereq'
            continue

        # handle numbered step lines like '1. Step 1: ...' or '1) Step 1: ...' or '1. Do this'
        m_num_step = re.match(r'^\s*\d+[\.)]\s*(.*)$', raw)
        if m_num_step:
            content = m_num_step.group(1).strip()
            if content:
                # if content begins with 'Step', preserve; else treat as step text
                if re.match(r'^step\s*\d+\s*:', content, re.IGNORECASE):
                    step_lines.append('- ' + content)
                else:
                    step_lines.append('- ' + content)
            # keep mode as steps
            mode = 'steps'
            continue

        # detect the headings
        if re.match(r'^\s*prerequisites\s*:\s*$', raw, re.IGNORECASE):
            mode = 'prereq'
            continue
        if re.match(r'^\s*step[- ]?by[- ]?step path\s*:\s*$', raw, re.IGNORECASE) or re.match(r'^\s*step\s*-?\s*\d+\s*:', raw, re.IGNORECASE):
            mode = 'steps'
            # if this line itself is a "Step 1: ..." title, treat as step title
            if re.match(r'^step\s*\d+\s*:', raw, re.IGNORECASE):
                step_lines.append(raw)
            continue

        # collect prereqs
        if mode == 'prereq' and raw.startswith('-'):
            item = re.sub(r'^[-\s]+', '', raw)
            prereq_items.append(item)
            continue

        # collect steps: accept lines starting with '-' or 'Step N:'
        if mode == 'steps' and (raw.startswith('-') or re.match(r'^step\s*\d+\s*:', raw, re.IGNORECASE)):
            if raw.startswith('-'):
                step_lines.append(raw)
            else:
                step_lines.append('- ' + raw)
            continue

        # fallback: if we haven't seen headings, attempt to parse known patterns
        if raw.startswith('-'):
            # treat as step if looks like 'Step' inside, else accumulate
            content = re.sub(r'^[-\s]+', '', raw)
            if re.match(r'^step\s*\d+\s*:', content, re.IGNORECASE):
                step_lines.append('- ' + content)
            else:
                # ambiguous: add to prereqs if we have none yet, else as step
                if not prereq_items:
                    prereq_items.append(content)
                else:
                    step_lines.append('- ' + content)

    # If no explicit prerequisites were detected, synthesize one from the task title
    if not prereq_items and step_lines:
        brief = ' '.join(sentence.split()[:6]).rstrip('.')
        prereq_items.append(f'Basic familiarity with {brief}')

    # build unified outline: one Prerequisites bullet, then step bullets
    out_lines = []
    if prereq_items:
        # join prerequisites with semicolons into a single bullet
        joined = '; '.join([p.rstrip('.') for p in prereq_items])
        out_lines.append('Prerequisites:')
        out_lines.append(f'- {joined}')

    if step_lines:
        out_lines.append('Step-by-step path:')
        # preserve original bullet text; keep order and limit to 5
        normalized_steps = []
        for s in step_lines:
            text = re.sub(r'^[-\s]+', '', s).strip()
            normalized_steps.append(text)

        for st in normalized_steps[:5]:
            out_lines.append(f'- {st}')

    if not out_lines and raw_output:
        return raw_output.strip()

    return '\n'.join(out_lines)


_QUIZ_DOMAIN_KEYWORDS = {
    'dbms': (
        'database', 'dbms', 'sql', 'schema', 'table', 'relation', 'attribute', 'normalization',
        'functional dependency', 'candidate key', 'primary key', 'foreign key', 'partial dependency',
        'transitive dependency', '1nf', '2nf', '3nf', 'bcnf', 'redundancy', 'anomaly', 'decomposition',
    ),
    'os': (
        'operating system', 'deadlock', 'mutex', 'semaphore', 'starvation', 'paging', 'page fault',
        'process', 'thread', 'scheduling', 'critical section', 'circular wait', 'mutual exclusion',
    ),
    'networking': (
        'network', 'tcp', 'udp', 'handshake', 'routing', 'routing table', 'subnet', 'subnet mask',
        'ip', 'dns', 'packet', 'port', 'protocol', 'switch', 'router',
    ),
    'dsa': (
        'algorithm', 'recursion', 'recursive', 'bfs', 'dfs', 'heap', 'heapify', 'stack', 'queue',
        'tree', 'graph', 'time complexity', 'space complexity', 'sorting', 'searching',
    ),
    'programming': (
        'programming', 'output', 'debug', 'syntax', 'function', 'loop', 'class', 'object', 'exception',
        'pointer', 'reference', 'array', 'string', 'runtime', 'bug', 'variable',
    ),
}

def _normalize_quiz_phrase(text):
    return re.sub(r'\s+', ' ', str(text or '').strip())


def _extract_technical_concepts(title, summary_text):
    source_text = f"{title or ''}\n{summary_text or ''}"
    concepts = []
    seen = set()

    def add_concept(raw_value):
        concept = _normalize_quiz_phrase(raw_value).strip(' .:-')
        if not concept:
            return
        lowered = concept.lower()
        if lowered in seen:
            return
        if len(lowered) < 2:
            return
        if lowered in {'guide', 'step', 'steps', 'path', 'prerequisites', 'learning', 'topic'}:
            return
        seen.add(lowered)
        concepts.append(concept)

    source_text = re.sub(r'\b(guide|prerequisites|step-by-step path)\s*:\s*', '\n', source_text, flags=re.IGNORECASE)

    for line in source_text.splitlines():
        line = _normalize_quiz_phrase(line)
        if not line:
            continue
        line = re.sub(r'^(guide|prerequisites|step-by-step path)\s*:\s*', '', line, flags=re.IGNORECASE)
        line = re.sub(r'^step\s*\d+\s*:\s*', '', line, flags=re.IGNORECASE)
        line = re.sub(r'^\d+[\.)]\s*', '', line)

        chunks = re.split(r'[;•,|/]+', line)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            for part in re.split(r'\s+-\s+', chunk):
                part = part.strip()
                if not part:
                    continue
                cleaned = re.sub(r'^(define|identify|apply|remove|learn|understand|study|determine|validate|test|refine|continue to refine)\s+', '', part, flags=re.IGNORECASE)
                add_concept(cleaned)

    for token in re.findall(r'\b(?:\d+NF|BCNF|BFS|DFS|TCP|UDP|SQL|DBMS|OS|IP|DNS|FIFO|LIFO|FCFS|SJF|RR)\b', source_text, flags=re.IGNORECASE):
        add_concept(token)

    # Final sanitization: remove UI/metadata tokens and keep only technical terms
    BLACKLIST = {
        'learning', 'moderate', 'hard', 'easy', 'category', 'guide', 'task', 'roadmap',
        'step', 'steps', 'prerequisite', 'prerequisites', 'question', 'quiz', 'title',
        'difficulty', 'description', 'summary', 'note', 'notes', 'example'
    }

    TECHNICAL_KEYWORDS = set(k.lower() for k in (
        # DBMS / data
        'database', 'dbms', 'sql', 'schema', 'table', 'relation', 'attribute', 'normalization',
        'functional dependency', 'candidate key', 'primary key', 'foreign key', 'partial dependency',
        'transitive dependency', '1nf', '2nf', '3nf', 'bcnf', 'redundancy', 'anomaly', 'decomposition',
        'index', 'join', 'transaction', 'commit', 'rollback', 'isolation', 'consistency',
        # OS
        'deadlock', 'mutex', 'semaphore', 'starvation', 'paging', 'page fault', 'process', 'thread',
        'scheduling', 'critical section', 'circular wait', 'mutual exclusion', 'context switch',
        # Networking
        'tcp', 'udp', 'handshake', 'routing', 'routing table', 'subnet', 'subnet mask', 'ip', 'dns',
        'packet', 'port', 'protocol', 'switch', 'router', 'arp', 'icmp',
        # DSA
        'algorithm', 'recursion', 'bfs', 'dfs', 'heap', 'heapify', 'stack', 'queue', 'tree', 'graph',
        'time complexity', 'space complexity', 'sorting', 'searching', 'binary', 'hash',
        # Programming / infra
        'api', 'endpoint', 'http', 'rest', 'grpc', 'docker', 'kubernetes', 'thread', 'lock', 'mutex',
        'exception', 'memory leak', 'pointer', 'reference', 'array', 'string', 'buffer',
    ))

    def is_technical(concept):
        cl = concept.lower()
        # reject if exactly a blacklisted token or contains a blacklisted token as a whole word
        for b in BLACKLIST:
            if re.search(r'\b' + re.escape(b) + r'\b', cl):
                return False

        # technical if contains any technical keyword
        for tk in TECHNICAL_KEYWORDS:
            if tk in cl:
                return True

        # accept common acronyms / code-like tokens
        if re.search(r'\b[A-Z0-9]{2,}\b', concept):
            return True

        # accept multi-word concepts that include hyphens or slashes or digits (likely technical)
        if re.search(r'[\-/]|\d', concept):
            return True

        # otherwise reject as non-technical
        return False

    filtered = []
    for c in concepts:
        if is_technical(c):
            filtered.append(c)

    # If nothing technical found, attempt a conservative extraction from title (tokenize and filter)
    if not filtered:
        title_tokens = [t for t in re.findall(r"[A-Za-z0-9\+\-]{2,}", title or '')]
        for t in title_tokens:
            if is_technical(t):
                filtered.append(t)

    # final dedupe & limit
    seen_final = set()
    final = []
    for item in filtered:
        key = item.lower()
        if key in seen_final:
            continue
        seen_final.add(key)
        final.append(item)

    print(f"[AI] Extracted technical concepts: {final}")
    return final[:10]


def _classify_quiz_domain(title, summary_text, concepts):
    source_text = f"{title or ''} {summary_text or ''} {' '.join(concepts or [])}".lower()
    scores = {domain: 0 for domain in _QUIZ_DOMAIN_KEYWORDS}

    for domain, keywords in _QUIZ_DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in source_text:
                scores[domain] += 1

    best_domain = max(scores, key=scores.get)
    return best_domain if scores[best_domain] else 'general'


_QUIZ_FORBIDDEN_PHRASES = (
    'main idea',
    'best matches',
    'understanding the topic',
    'what should',
    'quiz',
    'topic',
    'learning guide',
)

_QUIZ_GENERIC_DISTRACTORS = (
    'random unrelated subject',
    'formatting issue',
    'time management',
    'clicked the right button',
    'submission speed',
    'random workflow detail',
    'generic workflow',
)


def _build_quiz_prompt(title, summary_text, difficulty, concepts, domain, question_count, rejected_output=None, rejection_reason=None):
    concept_block = '\n'.join(f'- {concept}' for concept in concepts[:10]) if concepts else '- No extracted concepts available'
    source_block = summary_text or 'No extra summary available.'
    rejected_block = ''
    if rejected_output:
        rejected_block = f"\nPrevious output rejected for being too generic or invalid:\n{rejected_output}\n"
        if rejection_reason:
            rejected_block += f"Reason: {rejection_reason}\n"

    return f"""
You are generating a real technical assessment with natural interview-style MCQs.

Task title: {title}
Domain: {domain}
Difficulty: {difficulty}

Source material:
{source_block}

Extracted concepts to use:
{concept_block}

Rules:
1. Return ONLY valid JSON.
2. Return a JSON array with exactly {question_count} objects.
3. Each object must have: question, options, answer, explanation.
4. Each question must be a real technical MCQ grounded in the source material and extracted concepts.
5. Mix styles across the set: scenario-based, debugging-based, implementation-based, output prediction, edge case, or real-world failure.
6. Use varied sentence structure. Do not repeat the same phrasing pattern.
7. Do not use meta or educational language such as: main idea, best matches, understanding the topic, what should, quiz, topic, learning guide.
8. Do not use placeholder distractors or generic fillers such as random unrelated subject, formatting issue, time management, clicked the right button.
9. Distractors must be technically plausible and domain-aware.
10. Keep each question focused on a specific concept from the extracted list.
11. Avoid reusing the same opening words or structure across questions.
12. Use concise explanations that justify the correct answer technically.
13. Questions should feel like exam, certification, or interview questions.
14. Do not mention that the content came from a guide.
15. Do not ask about the quiz itself.
{rejected_block}

Generate the quiz now.
""".strip()


def _question_contains_forbidden_language(text):
    normalized = _normalize_quiz_phrase(text).lower()
    return any(phrase in normalized for phrase in _QUIZ_FORBIDDEN_PHRASES)


def _question_uses_concept(question_text, concepts, domain):
    question_lower = _normalize_quiz_phrase(question_text).lower()
    concept_terms = [concept.lower() for concept in concepts or [] if len(concept) > 1]
    if any(term in question_lower for term in concept_terms):
        return True

    domain_terms = [term.lower() for term in _QUIZ_DOMAIN_KEYWORDS.get(domain, ())]
    return any(term in question_lower for term in domain_terms)


def _normalize_question_item(item, concepts, domain):
    if not isinstance(item, dict):
        return None

    question = _normalize_quiz_phrase(item.get('question'))
    options = [str(option).strip() for option in (item.get('options') or []) if str(option).strip()]
    answer = _normalize_quiz_phrase(item.get('answer'))
    explanation = _normalize_quiz_phrase(item.get('explanation'))

    if not question or not explanation:
        return None
    if len(options) != 4:
        return None
    if answer not in options:
        return None
    if _question_contains_forbidden_language(question):
        return None
    if any(_question_contains_forbidden_language(option) for option in options):
        return None
    if any(_question_contains_forbidden_language(text) for text in (answer, explanation)):
        return None
    if any(distractor in ' '.join(options).lower() for distractor in _QUIZ_GENERIC_DISTRACTORS):
        return None
    if not _question_uses_concept(question, concepts, domain):
        return None
    if len(set(option.lower() for option in options)) != 4:
        return None

    return {
        'question': question,
        'options': options,
        'answer': answer,
        'explanation': explanation,
    }


def _validate_quiz_response(parsed, concepts, domain, question_count):
    if not isinstance(parsed, list):
        return []

    cleaned = []
    seen_questions = set()
    for item in parsed:
        normalized = _normalize_question_item(item, concepts, domain)
        if not normalized:
            continue
        question_key = normalized['question'].lower()
        if question_key in seen_questions:
            continue
        seen_questions.add(question_key)
        cleaned.append(normalized)
        if len(cleaned) >= question_count:
            break

    return cleaned


def _fallback_quiz_questions(title, summary_text, difficulty, concepts=None, domain='general'):
    concepts = concepts or _extract_technical_concepts(title, summary_text)
    concepts = concepts[:5] if concepts else [_normalize_quiz_phrase(title or 'the concept')]
    cleaned = []
    for index, concept in enumerate(concepts[:5]):
        lower_concept = concept.lower()
        if domain == 'dbms':
            if index == 0:
                cleaned.append({
                    'question': f'If {concept} is stored in multiple places, what issue is most likely to appear?',
                    'options': ['Update anomaly', 'TCP congestion', 'Stack overflow', 'Deadlock'],
                    'answer': 'Update anomaly',
                    'explanation': 'Repeated values in related records can cause update anomalies.',
                })
            elif index == 1:
                cleaned.append({
                    'question': f'Which dependency should be removed if {concept} depends only on part of a composite key?',
                    'options': ['Partial dependency', 'Circular wait', 'Mutex lock', 'Packet loss'],
                    'answer': 'Partial dependency',
                    'explanation': 'A partial dependency violates 2NF.',
                })
            elif index == 2:
                cleaned.append({
                    'question': f'When {concept} creates a chain between non-key attributes, what normal form is affected?',
                    'options': ['3NF', '1NF', 'Paging', 'BFS'],
                    'answer': '3NF',
                    'explanation': 'Transitive dependencies are removed in 3NF.',
                })
            elif index == 3:
                cleaned.append({
                    'question': f'What is the usual fix when {concept} still causes redundancy after normalization?',
                    'options': ['Decompose the relation further', 'Add repeated columns', 'Merge all tables', 'Disable constraints'],
                    'answer': 'Decompose the relation further',
                    'explanation': 'Further decomposition can remove remaining redundancy.',
                })
            else:
                cleaned.append({
                    'question': f'What is the best check after applying {concept} to a table with anomalies?',
                    'options': ['Verify that the remaining dependencies are removed', 'Ignore the anomalies', 'Add random attributes', 'Convert the table to text'],
                    'answer': 'Verify that the remaining dependencies are removed',
                    'explanation': 'You validate whether the decomposition removed the problematic dependency.',
                })
        else:
            cleaned.append({
                'question': f'How does {concept} behave in a real implementation scenario?',
                'options': [f'It changes the program state or behavior in a specific way', 'It only changes formatting', 'It has no runtime effect', 'It replaces the topic with another subject'],
                'answer': 'It changes the program state or behavior in a specific way',
                'explanation': f'This is a minimal emergency fallback tied to {lower_concept}.',
            })

    return cleaned[:5]


def generateTechnicalMCQ(
    concepts,
    domain,
    title,
    summary_text,
    difficulty='Moderate',
    question_count=5
):
    questions = []
    attempts = 3
    rejection_reason = None
    rejected_output = None

    for attempt in range(attempts):
        prompt = _build_quiz_prompt(
            title=title,
            summary_text=summary_text,
            difficulty=difficulty,
            concepts=concepts,
            domain=domain,
            question_count=question_count,
            rejected_output=rejected_output,
            rejection_reason=rejection_reason,
        )
        raw_output = call_groq_api(prompt, max_completion_tokens=2200, temperature=0.4 if attempt == 0 else 0.6)
        if not raw_output:
            rejected_output = raw_output
            rejection_reason = 'empty response'
            continue

        try:
            parsed = json.loads(raw_output)
        except Exception:
            rejected_output = raw_output
            rejection_reason = 'invalid JSON'
            continue

        questions = _validate_quiz_response(parsed, concepts, domain, question_count)
        if len(questions) >= question_count:
            return questions[:question_count]

        rejected_output = raw_output
        rejection_reason = 'questions failed validation'

    return _fallback_quiz_questions(title, summary_text, 'Moderate', concepts=concepts, domain=domain)[:question_count]


def generate_task_quiz_with_ai(title, summary_text='', difficulty='Moderate', question_count=5):
    """
    Creates 5-7 MCQ questions for a completed task.
    """
    question_count = max(5, min(int(question_count or 5), 7))
    concepts = _extract_technical_concepts(title, summary_text)
    domain = _classify_quiz_domain(title, summary_text, concepts)
    questions = generateTechnicalMCQ(
    concepts,
    domain,
    title,
    summary_text,
    difficulty=difficulty,
    question_count=question_count
)

    if len(questions) < question_count:
        questions = (questions + _fallback_quiz_questions(title, summary_text, difficulty, concepts=concepts, domain=domain))[:question_count]

    return questions[:question_count]


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