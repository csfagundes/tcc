import os
import json
import time
import base64
import getpass
import pandas as pd
import anthropic
from curl_cffi import requests as cffi_requests

ARQUIVO_ENTRADA   = "cartoes_brasileirao_2018_2023.csv"
ARQUIVO_SAIDA     = "cartoes_com_raca.xlsx"
CHECKPOINT        = "checkpoint_classificacao.json"
DELAY_ENTRE_CALLS = 1.0

PROMPT_SISTEMA = (
    "You are a research assistant for an academic study on racial bias in Brazilian football "
    "officiating (Serie A 2018-2023), using the heteroidentification methodology from "
    "Silva, Bastos and Silva (Revista Movimento, 2025).\n\n"
    "Classify the athlete phenotypical skin color using 3 simplified IBGE categories:\n"
    "- Branco: light skin, predominantly European features\n"
    "- Pardo: intermediate/brown skin, mixed features\n"
    "- Preto: dark skin, predominantly Afro-descendant features\n\n"
    "Reply ONLY with valid JSON. No prose, no markdown, no code fences.\n"
    "Schema: {\"classificacao\":\"Branco\",\"confianca\":\"alta\",\"justificativa\":\"one sentence\"}\n"
    "confianca: alta | media | baixa"
)


def carregar_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_checkpoint(resultados):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


def baixar_imagem_base64(session, url):
    r = session.get(url, timeout=15)
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    if content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        content_type = "image/jpeg"
    return base64.standard_b64encode(r.content).decode("utf-8"), content_type


def classificar_jogador(client, session, player_name, photo_url):
    img_b64, media_type = baixar_imagem_base64(session, photo_url)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=PROMPT_SISTEMA,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64,
                    }
                },
                {
                    "type": "text",
                    "text": "Classify athlete " + player_name + ". JSON only."
                }
            ]
        }]
    )
    raw = msg.content[0].text.strip()
    return json.loads(raw)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Cole sua chave da API Anthropic (sk-ant-...) e pressione Enter.")
        print("A chave NAO ficara salva em nenhum arquivo.")
        api_key = getpass.getpass("API Key: ")

    client = anthropic.Anthropic(api_key=api_key)

    # curl_cffi impersonates Chrome TLS fingerprint - bypasses Cloudflare
    session = cffi_requests.Session(impersonate="chrome124")
    session.headers.update({
        "Referer"        : "https://www.sofascore.com/",
        "Accept"         : "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    if not os.path.exists(ARQUIVO_ENTRADA):
        print("ERRO: " + ARQUIVO_ENTRADA + " nao encontrado.")
        return

    print("Carregando " + ARQUIVO_ENTRADA + "...")
    df = pd.read_csv(ARQUIVO_ENTRADA)
    print(str(len(df)) + " cartoes | " + str(df["player_id"].nunique()) + " jogadores unicos")

    jogadores = (
        df[["player_id", "player_name", "player_photo_url"]]
        .drop_duplicates("player_id")
        .dropna(subset=["player_photo_url"])
        .reset_index(drop=True)
    )

    resultados = carregar_checkpoint()
    ja_ok = {pid for pid, v in resultados.items() if v.get("classificacao") is not None}
    pendentes = jogadores[~jogadores["player_id"].astype(str).isin(ja_ok)]
    total     = len(jogadores)
    ja_feitos = len(ja_ok)

    print("Ja classificados: " + str(ja_feitos) + "/" + str(total))
    print("Restantes: " + str(len(pendentes)))

    erros = 0
    for i, (_, row) in enumerate(pendentes.iterrows(), start=1):
        pid      = str(row["player_id"])
        nome     = str(row["player_name"])
        foto_url = str(row["player_photo_url"])

        print("[" + str(ja_feitos + i) + "/" + str(total) + "] " + nome + " ... ", end="", flush=True)

        tentativas = 0
        while tentativas < 3:
            try:
                resultado = classificar_jogador(client, session, nome, foto_url)
                resultados[pid] = resultado
                salvar_checkpoint(resultados)
                print(str(resultado.get("classificacao", "?")) + " (" + str(resultado.get("confianca", "?")) + ")")
                break
            except Exception as e:
                tentativas += 1
                if tentativas < 3:
                    print("erro, tentando novamente (" + str(tentativas) + "/3)...", end=" ", flush=True)
                    time.sleep(3)
                else:
                    print("FALHOU: " + str(e))
                    resultados[pid] = {"classificacao": None, "confianca": None, "justificativa": str(e)}
                    salvar_checkpoint(resultados)
                    erros += 1

        time.sleep(DELAY_ENTRE_CALLS)

    print("Classificacao concluida. Erros: " + str(erros))
    print("Gerando " + ARQUIVO_SAIDA + "...")

    df["player_id"]     = df["player_id"].astype(str)
    df["classificacao"] = df["player_id"].map(lambda p: resultados.get(p, {}).get("classificacao"))
    df["confianca"]     = df["player_id"].map(lambda p: resultados.get(p, {}).get("confianca"))
    df["justificativa"] = df["player_id"].map(lambda p: resultados.get(p, {}).get("justificativa"))

    df.to_excel(ARQUIVO_SAIDA, index=False)
    print("Salvo: " + ARQUIVO_SAIDA)
    print(str(df.drop_duplicates("player_id")["classificacao"].value_counts()))


if __name__ == "__main__":
    main()
