# Agente personale locale

Assistente in italiano che gira interamente in locale, senza API a pagamento.
Fa tre cose: conversare con memoria, cercare sul web con fonti e scrivere ed eseguire codice Python.

## Modello

- **Modello:** `llama3.2:3b` (3 miliardi di parametri)
- **Runtime:** [Ollama](https://ollama.com), eseguito in un container Docker (`its_ollama`), porta `11435`
- **Ricerca web:** DuckDuckGo tramite la libreria `ddgs`

Il modello si cambia modificando la variabile `MODEL` in `agent_multi.py`.

## Come funziona

Il modello è piccolo, quindi le decisioni le prende il codice, non il modello:

| Se la frase contiene | Cosa succede |
|---|---|
| `programma`, `codice`, `.py`, `esegui` | il modello scrive il codice, il programma lo salva in `workspace/` e lo esegue |
| `cerca`, `ricerca`, `sul web`, `online` | ricerca vera su DuckDuckGo, il modello riassume solo i risultati e mostra le fonti |
| `ricorda: ...` | salva la frase in `note.md` |
| altro | conversazione normale |

## Memoria

- `note.md`: cose da ricordare per sempre (scritte con `ricorda:`)
- `storia.json`: ultimi 20 messaggi

## Installazione

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
docker exec -it its_ollama ollama pull llama3.2:3b
python3 agent_multi.py
```

## Esempi

```
cerca sul web cos'è Ollama
scrivi un programma che stampa i numeri da 1 a 5, salvalo in uno.py ed eseguilo
ricorda: sto lavorando al mio progetto
```

## Limiti

- Un modello da 3B sbaglia facilmente con richieste lunghe o complesse.
- Il codice generato va sempre controllato in `workspace/`.
- Il programma non gestisce codice che chiede input con `input()`.