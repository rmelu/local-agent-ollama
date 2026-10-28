import re, subprocess, sys
from pathlib import Path

import ollama
from ddgs import DDGS

MODEL = "llama3.2:3b"
client = ollama.Client(host="http://localhost:11435")

WORKDIR = Path("workspace").resolve()
WORKDIR.mkdir(exist_ok=True)


# ---------- STRUMENTI DI BASE ----------
def safe_path(name: str) -> Path:
    p = (WORKDIR / name).resolve()
    if WORKDIR not in p.parents and p != WORKDIR:
        raise ValueError("Percorso fuori dalla cartella workspace")
    return p


def web_search(query: str) -> str:
    """Cerca sul web e restituisce i primi risultati.

    Args:
        query: il testo da cercare
    """
    try:
        res = DDGS().text(query, max_results=5)
        return "\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in res) or "Nessun risultato"
    except Exception as e:
        return f"Errore nella ricerca: {e}"


def read_file(name: str) -> str:
    """Legge un file dalla cartella workspace.

    Args:
        name: nome del file
    """
    return safe_path(name).read_text()[:5000]


def write_file(name: str, content: str) -> str:
    """Scrive un file nella cartella workspace.

    Args:
        name: nome del file
        content: contenuto completo del file
    """
    safe_path(name).write_text(content)
    return f"File {name} scritto."


def run_python(name: str) -> str:
    """Esegue un file Python della cartella workspace e restituisce l'output.

    Args:
        name: nome del file .py da eseguire
    """
    r = subprocess.run(
        [sys.executable, str(safe_path(name))],
        capture_output=True, text=True, timeout=30, cwd=WORKDIR,
    )
    return (r.stdout + r.stderr)[:3000] or "(nessun output)"


# ---------- IL CICLO DELL'AGENTE ----------
def run_agent(messages: list, tools: list, label: str, max_steps: int = 6) -> str:
    registry = {f.__name__: f for f in tools}
    for _ in range(max_steps):
        resp = client.chat(model=MODEL, messages=messages, tools=tools or None)
        msg = resp.message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            name, args = call.function.name, call.function.arguments
            if any(not isinstance(v, str) for v in args.values()):
                messages.append({"role": "tool", "tool_name": name,
                                 "content": "Errore: il parametro deve essere una stringa di testo. Riprova."})
                continue
            print(f"  [{label}] usa {name}({args})")
            try:
                result = registry[name](**args) if name in registry else "Strumento inesistente"
            except Exception as e:
                result = f"Errore: {e}"
            messages.append({"role": "tool", "tool_name": name, "content": str(result)})
    return "Limite di passi raggiunto."


# ---------- PROGRAMMATORE DIRETTO (salva ed esegue il codice, senza tool calling) ----------
def programmer_direct(task: str) -> str:
    resp = client.chat(model=MODEL, messages=[
        {"role": "system", "content":
            "Sei un programmatore Python. Rispondi SOLO con codice Python valido "
            "dentro un blocco ```python. Nessuna spiegazione. "
            "Usa la sintassi Python vera: for, if, print (non parole italiane)."},
        {"role": "user", "content": task},
    ])
    text = resp.message.content
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    code = m.group(1) if m else text

    nome = re.search(r"(\w+\.py)", task)
    path = safe_path(nome.group(1) if nome else "script.py")
    path.write_text(code)

    r = subprocess.run([sys.executable, str(path)],
                       capture_output=True, text=True, timeout=30, cwd=WORKDIR)
    return f"File salvato in {path}\n\nCodice:\n{code}\n\nOutput:\n{r.stdout}{r.stderr}"


# ---------- AGENTE 2: RICERCATORE ----------
RESEARCHER_SYSTEM = (
    "Sei un ricercatore. Usi web_search per trovare informazioni e rispondi in italiano "
    "con un riassunto breve e preciso. Non inventare: se non trovi nulla, dillo."
)

def ask_researcher(task: str) -> str:
    # togliamo le parole di comando per ottenere la query pulita
    query = task.lower()
    for w in ["cerca sul web", "cerca online", "cerca", "ricerca", "sul web", "online"]:
        query = query.replace(w, "")
    query = query.strip() or task

    print(f"  [ricercatore] cerco: {query}")
    risultati = web_search(query)

    if risultati.startswith("Errore") or risultati == "Nessun risultato":
        return "Non sono riuscito a cercare: " + risultati

    resp = client.chat(model=MODEL, messages=[
        {"role": "system", "content":
            "Rispondi in italiano in modo breve. Usa SOLO le informazioni dei risultati "
            "di ricerca che ti vengono dati. Non aggiungere nulla di tuo. "
            "Se i risultati non bastano, dillo."},
        {"role": "user", "content": f"Domanda: {query}\n\nRisultati:\n{risultati}"},
    ])
    return resp.message.content + "\n\nFonti:\n" + "\n".join(
        line for line in risultati.splitlines() if line.startswith("http"))

# ---------- AGENTE 3: PROGRAMMATORE ----------
PROGRAMMER_SYSTEM = (
    "Sei un programmatore Python. Devi SEMPRE usare gli strumenti, non rispondere a memoria. "
    "Passo 1: salva il codice con write_file. "
    "Passo 2: eseguilo con run_python. "
    "Passo 3: se c'è un errore, correggilo e riprova. "
    "Riporta in italiano solo l'output reale di run_python, senza inventare."
)


def ask_programmer(task: str) -> str:
    """Delega al programmatore la scrittura e l'esecuzione di codice Python.

    Args:
        task: cosa deve fare il programma, descritto in modo chiaro
    """
    msgs = [{"role": "system", "content": PROGRAMMER_SYSTEM},
            {"role": "user", "content": task}]
    return run_agent(msgs, [write_file, read_file, run_python], "programmatore")


# ---------- AGENTE 1: CERVELLO ----------
BRAIN_SYSTEM = (
    "Sei un assistente personale che parla italiano e risponde in modo breve. "
    "Le tue uniche capacità reali sono: conversare, cercare sul web "
    "(l'utente deve scrivere 'cerca ...') e scrivere ed eseguire programmi Python "
    "(l'utente deve scrivere 'scrivi un programma ... salvalo in nome.py'). "
    "Non hai accesso a email, calendario o altri servizi: se ti chiedono altro, dillo chiaramente. "
    "Non inventare mai capacità che non hai."
)

import json
NOTES = Path("note.md")        # cose che voglio che ricordi per sempre
HISTORY = Path("storia.json")  # ultime conversazioni

def build_system():
    notes = NOTES.read_text() if NOTES.exists() else ""
    if notes:
        return BRAIN_SYSTEM + "\n\nInformazioni sull'UTENTE con cui parli (non su di te):\n" + notes
    return BRAIN_SYSTEM

storia = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
brain_messages = [{"role": "system", "content": build_system()}] + storia

while True:
    user = input("\nTu> ").strip()
    if user in ("exit", "quit"):
        break

    if user.lower().startswith("ricorda:"):
        with NOTES.open("a") as f:
            f.write("- " + user[8:].strip() + "\n")
        print("\nAgente> Ok, me lo ricordo.")
        continue

    if any(k in user.lower() for k in ["programma", "codice", ".py", "esegui"]):
        answer = programmer_direct(user)

    elif any(k in user.lower() for k in ["cerca", "ricerca", "sul web", "online"]):
        answer = ask_researcher(user)

    else:
        brain_messages.append({"role": "user", "content": user})
        resp = client.chat(model=MODEL, messages=brain_messages)
        answer = resp.message.content

    print("\nAgente>", answer)

    storia += [{"role": "user", "content": user},
               {"role": "assistant", "content": answer}]
    storia = storia[-20:]
    brain_messages = [{"role": "system", "content": build_system()}] + storia
    HISTORY.write_text(json.dumps(storia, ensure_ascii=False))
