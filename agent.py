import subprocess
from pathlib import Path

import ollama
from ddgs import DDGS

MODEL = "llama3.2:3b"
client = ollama.Client(host="http://localhost:11435")

WORKDIR = Path("workspace").resolve()
WORKDIR.mkdir(exist_ok=True)

SYSTEM = (
    "Sei un assistente personale che parla italiano. Aiuti con studio e programmazione. "
    "Usa gli strumenti solo quando servono: web_search per informazioni aggiornate, "
    "write_file e run_python per scrivere ed eseguire codice. "
    "Se non sai una cosa, dillo invece di inventare."
)


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
    """Esegue un file Python che sta nella cartella workspace e restituisce l'output.

    Args:
        name: nome del file .py da eseguire
    """
    r = subprocess.run(
        ["python3", str(safe_path(name))],
        capture_output=True, text=True, timeout=30, cwd=WORKDIR,
    )
    return (r.stdout + r.stderr)[:3000] or "(nessun output)"


TOOLS = {f.__name__: f for f in [web_search, read_file, write_file, run_python]}

messages = [{"role": "system", "content": SYSTEM}]

while True:
    user = input("\nTu> ").strip()
    if user in ("exit", "quit"):
        break
    messages.append({"role": "user", "content": user})

    for _ in range(8):
        resp = client.chat(model=MODEL, messages=messages, tools=list(TOOLS.values()))
        msg = resp.message
        messages.append(msg)
        if not msg.tool_calls:
            print("\nAgente>", msg.content)
            break
        for call in msg.tool_calls:
            name, args = call.function.name, call.function.arguments
            print(f"  [strumento] {name}({args})")
            try:
                result = TOOLS[name](**args) if name in TOOLS else "Strumento inesistente"
            except Exception as e:
                result = f"Errore: {e}"
            messages.append({"role": "tool", "tool_name": name, "content": str(result)})
    else:
        print("Raggiunto il limite di passi.")
