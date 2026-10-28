# -*- coding: utf-8 -*-
"""Assistente FP: janela Windows + Ollama local. Somente biblioteca padrao.

Nao executa shell/comandos criados pela IA; permite apenas acoes fixas e seguras.
"""
import json
import difflib
import time
import os
import queue
import re
import subprocess
import threading
import unicodedata
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

API = "http://127.0.0.1:11434"
MODEL_DEFAULT = "qwen3:4b-instruct"
APP_TITLE = "Assistente FP  |  IA Local + Voz"
BG = "#10131c"
PANEL = "#1b2030"
PANEL_2 = "#252b3b"
TEXT = "#f1f3f9"
MUTED = "#acb6ca"
ACCENT = "#8c79ff"
GREEN = "#67dda7"
RED = "#ff8c96"

PROGRAMAS = {
    "calculadora": "calc.exe",
    "bloco de notas": "notepad.exe",
    "paint": "mspaint.exe",
    "explorador": "explorer.exe",
}
EXTENSOES = {".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".jpg", ".jpeg", ".png", ".md", ".csv", ".odt"}
STOPWORDS = {"abra", "abrir", "abre", "meu", "minha", "meus", "minhas", "o", "a", "os", "as", "um", "uma", "de", "da", "do", "na", "no", "em", "pasta", "arquivo", "arquivos", "procure", "procurar", "pesquise", "buscar", "busque", "encontre", "localize", "com", "nome", "chamado", "chamada", "por", "favor", "pra", "para", "quero", "ver", "um", "documento"}


# Descoberta limitada a atalhos existentes no Menu Iniciar: o modelo
# jamais fornece um executável, comando shell ou caminho executável a lançar.
PALAVRAS_IGNORADAS_APPS = {"o", "a", "os", "as", "um", "uma", "meu", "minha", "favor", "por", "pra", "para", "aplicativo", "programa", "app", "do", "da"}
ATALHOS_EXCLUIDOS = ("uninstall", "desinstal", "update", "atualiz", "setup", "instalar", "readme", "manual", "help", "licen", "suporte")


def catalogo_apps():
    """Retorna shortcuts da conta e do Menu Iniciar comum, em ordem determinística."""
    pastas = [
        Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs',
        Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Microsoft/Windows/Start Menu/Programs',
    ]
    apps = {}
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for atalho in pasta.rglob('*.lnk'):
            if atalho.is_symlink():
                continue
            nome = normalizar(atalho.stem)
            if any(ruim in nome for ruim in ATALHOS_EXCLUIDOS):
                continue
            if nome and nome not in apps:
                apps[nome] = atalho
            if len(apps) > 3000:
                break
    return apps


def nome_programa_da_frase(frase):
    t = normalizar(frase)
    t = re.sub(r"\b(abre|abra|abrir|inicia|inicie|iniciar|executa|execute|executar|abre ai)\b", " ", t)
    return ' '.join(p for p in t.split() if p not in PALAVRAS_IGNORADAS_APPS).strip()


def localizar_app(nome):
    """Retorna (nome, destino, exato). Sem matching inseguro por padrão."""
    nome = normalizar(nome)
    aliases = {
        'calc': 'calculadora', 'calculador': 'calculadora',
        'notepad': 'bloco de notas', 'bloco': 'bloco de notas',
        'explorer': 'explorador', 'arquivos': 'explorador',
        'google chrome': 'chrome', 'visual studio code': 'vs code',
        'microsoft edge': 'edge',
    }
    nome = aliases.get(nome, nome)
    if nome in PROGRAMAS or nome == 'navegador':
        return (nome, None, True)
    apps = catalogo_apps()
    if nome in apps:
        return (nome, apps[nome], True)
    # Para "abra chrome", muitos atalhos são "Google Chrome".
    unicos = [(n, p) for n, p in apps.items() if nome and (n.endswith(' ' + nome) or n.startswith(nome + ' '))]
    if len(unicos) == 1:
        n, p = unicos[0]
        return (n, p, True)
    proximos = difflib.get_close_matches(nome, sorted(apps), n=3, cutoff=0.64)
    if proximos:
        return (proximos[0], apps[proximos[0]], False)
    return None


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().split())


def http_json(path, payload=None, timeout=7):
    url = API + path
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.URLError as exc:
        raise ConnectionError("O Ollama não respondeu. Abra o aplicativo Ollama e tente novamente.") from exc


def pastas_usuario():
    home = Path.home()
    # Windows traduz visualmente os nomes; caminhos internos costumam estar em ingles.
    nomes = {"documentos": ["Documents", "Documentos"], "downloads": ["Downloads"], "area de trabalho": ["Desktop", "Área de Trabalho", "Area de Trabalho"]}
    lugares = [home] + [p for p in home.glob("OneDrive*") if p.is_dir()]
    encontrado = {}
    for chave, subpastas in nomes.items():
        for base in lugares:
            for sub in subpastas:
                pasta = base / sub
                if pasta.is_dir():
                    encontrado[chave] = pasta
                    break
            if chave in encontrado:
                break
    return encontrado


def pasta_para(texto):
    texto = normalizar(texto)
    if "download" in texto:
        return "downloads"
    if any(a in texto for a in ("document", "documento")):
        return "documentos"
    if any(a in texto for a in ("desktop", "area de trabalho")):
        return "area de trabalho"
    return "todas"


def nome_seguro(nome):
    if not isinstance(nome, str):
        return False
    if not nome or len(nome) > 100 or nome.strip() != nome or nome[-1] in ". ":
        return False
    if nome in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', nome):
        return False
    prefixo = nome.split(".", 1)[0].upper()
    return prefixo not in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def extrair_busca(frase):
    palavras = re.findall(r"[a-z0-9_-]+", normalizar(frase))
    palavras = [p for p in palavras if p not in STOPWORDS and p not in {"downloads", "download", "documentos", "documento", "desktop", "area", "trabalho"}]
    return " ".join(palavras).strip()


def buscar_arquivos(termo, local="todas"):
    termo = normalizar(termo)
    if len(termo) < 2:
        raise ValueError("Diga pelo menos dois caracteres do nome do arquivo.")
    pastas = pastas_usuario()
    if local != "todas" and local not in pastas:
        raise ValueError(f"A pasta '{local}' não foi encontrada no Windows.")
    raizes = [pastas[local]] if local != "todas" else list(dict.fromkeys(pastas.values()))
    if not raizes:
        raise ValueError("Não encontrei Documentos, Downloads ou Área de Trabalho.")
    resultados = []
    visitados = 0
    for raiz in raizes:
        for diretorio, subdirs, arquivos in os.walk(raiz, followlinks=False):
            subdirs[:] = [s for s in subdirs if s not in {".git", ".venv", "node_modules", "$RECYCLE.BIN"} and not s.startswith(".") and not (Path(diretorio) / s).is_symlink()]
            for arquivo in arquivos:
                visitados += 1
                nome = normalizar(arquivo)
                palavras = termo.split()
                if termo in nome or (palavras and all(p in nome for p in palavras)):
                    p = Path(diretorio) / arquivo
                    if p.is_file() and not p.is_symlink():
                        resultados.append(p)
                        if len(resultados) >= 12:
                            return resultados
                if visitados >= 30000:
                    return resultados
    return resultados


def comando_direto(frase):
    """Casos frequentes sem modelo: diminui erros do Qwen pequeno."""
    t = normalizar(frase)
    if not t:
        return None
    abre = re.search(r"\b(?:abra|abre|abrir|iniciar|inicie|executar|execute)\b", t)
    busca = re.search(r"\b(?:procure|procurar|pesquise|pesquisar|busque|buscar|encontre|encontrar|localize|localizar)\b", t)
    cria = re.search(r"\b(?:crie|cria|criar|faca|fazer)\b", t)
    if cria and "pasta" in t:
        # Ex.: "crie uma pasta chamada Faculdade em Documentos"
        match = re.search(r"pasta\s+(?:chamad[ao]\s+)?(.+?)\s+(?:em|nos?|nas?)\s+(documentos|downloads|area de trabalho|desktop)\b", t)
        if match:
            return {"acao": "criar_pasta", "nome": match.group(1).strip(), "pasta": pasta_para(match.group(2))}
        return {"acao": "responder", "mensagem": "Para criar uma pasta, tente: Crie uma pasta chamada Faculdade em Documentos."}
    if abre and ("pasta" in t or t in {"abra downloads", "abra documentos", "abra area de trabalho"}):
        local = pasta_para(t)
        if local != "todas":
            return {"acao": "abrir_pasta", "pasta": local}
    if (abre or busca) and ("curriculo" in t or "arquivo" in t or "documento" in t or busca):
        if "curriculo" in t:
            termo = "curriculo"
        else:
            termo = extrair_busca(frase)
        return {"acao": "buscar_arquivo", "consulta": termo, "pasta": pasta_para(t)}
    if abre:
        nome = nome_programa_da_frase(frase)
        if nome:
            if any(w in t for w in ('site ', 'pagina da internet')):
                return None
            return {"acao": "abrir_programa", "programa": nome}
    return None

INSTRUCOES = """Você interpreta pedidos em português para um assistente Windows. Retorne SOMENTE JSON válido com:
{"acao":"responder|abrir_programa|abrir_pasta|buscar_arquivo|criar_pasta","programa":"","pasta":"","nome":"","consulta":"","mensagem":""}.
Ações: abrir_programa (programa=nome simples do app, SEM CAMINHOS ou argumentos);
abrir_pasta (pasta=documentos, downloads ou area de trabalho);
buscar_arquivo (consulta=parte do nome, pasta=documentos,downloads,area de trabalho,todas);
criar_pasta (nome=nome simples, pasta=documentos, downloads ou area de trabalho).
Para 'abra meu currículo', BUSCAR_ARQUIVO com consulta 'curriculo'.
Se não for pedido para essas ações, acao=responder.
Não proponha PowerShell, terminal, exclusão, mudança de segurança, downloads ou leitura de arquivos.
"""


def classificar_por_ia(frase, modelo):
    dados = http_json("/api/chat", {"model": modelo, "messages": [
        {"role": "system", "content": INSTRUCOES},
        {"role": "user", "content": "Classifique este pedido e responda apenas JSON: " + frase},
    ], "format": "json", "stream": False, "options": {"temperature": 0}}, timeout=120)
    texto = dados.get("message", {}).get("content", "")
    resposta = json.loads(texto)
    if not isinstance(resposta, dict):
        raise ValueError("A IA não devolveu um comando válido.")
    return resposta


def conversar(frase, modelo, historico):
    hist = historico[-8:]
    mensagens = [{"role": "system", "content": "Você é o Assistente FP, uma IA local no computador do usuário. Responda em português de forma concisa. Você só controla aplicativos autorizados (calculadora, bloco de notas, paint, explorador, navegador), cria pastas em locais autorizados e pesquisa nomes de arquivos. Não afirme ter feito algo que não executou."}]
    mensagens.extend(hist)
    mensagens.append({"role": "user", "content": frase})
    dados = http_json("/api/chat", {"model": modelo, "messages": mensagens, "stream": False, "options": {"temperature": 0.4}}, timeout=120)
    return dados.get("message", {}).get("content", "").strip() or "Não consegui formular uma resposta."


class Interface:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x720")
        self.root.minsize(690, 570)
        self.root.configure(bg=BG)
        self.fila = queue.Queue()
        self.trabalhando = False
        self.arquivos = []
        self.historico = []
        self.modelo = tk.StringVar(value=MODEL_DEFAULT)
        self.voz = None
        self.escutando = False
        self.tempo_voz = None
        self.status = tk.StringVar(value="Conectando ao Ollama...")
        self._montar()
        self.root.after(90, self._processar_fila)
        self._verificar_modelos()

    def _montar(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 12))
        tk.Label(header, text="✦ Assistente FP", fg=TEXT, bg=BG, font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(header, text="IA local • Windows • Voz", fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(side="left", padx=(16, 0), pady=(9, 0))
        statusbar = tk.Frame(self.root, bg=BG)
        statusbar.pack(fill="x", padx=24, pady=(0, 14))
        self.status_label = tk.Label(statusbar, textvariable=self.status, fg=GREEN, bg=BG, font=("Segoe UI", 10))
        self.status_label.pack(side="left")
        tk.Label(statusbar, text="Modelo:", fg=MUTED, bg=BG).pack(side="left", padx=(25, 6))
        self.selector = ttk.Combobox(statusbar, textvariable=self.modelo, width=24, state="readonly")
        self.selector["values"] = [MODEL_DEFAULT]
        self.selector.pack(side="left")
        tk.Button(statusbar, text="Atualizar", command=self._verificar_modelos, bg=PANEL_2, fg=TEXT, relief="flat", cursor="hand2", padx=10).pack(side="left", padx=7)
        tk.Label(statusbar, text="Sem API paga • Microfone sob controle", fg=MUTED, bg=BG).pack(side="right")

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=24)
        chat_box = tk.Frame(main, bg=PANEL)
        chat_box.pack(fill="both", expand=True)
        tk.Label(chat_box, text="CONVERSA", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(13, 2))
        self.chat = tk.Text(chat_box, wrap="word", bg=PANEL, fg=TEXT, relief="flat", bd=0, font=("Segoe UI", 11), padx=16, pady=10, insertbackground=TEXT, state="disabled")
        self.chat.pack(fill="both", expand=True, padx=(0, 6), pady=(0, 6))
        self.chat.tag_configure("voce", foreground="#b4a8ff", font=("Segoe UI", 11, "bold"), spacing1=12)
        self.chat.tag_configure("ia", foreground=GREEN, font=("Segoe UI", 11, "bold"), spacing1=12)
        self.chat.tag_configure("corpo", foreground=TEXT, spacing3=8)
        self.chat.tag_configure("erro", foreground=RED, spacing3=8)

        resultados = tk.Frame(main, bg=BG)
        resultados.pack(fill="x", pady=(12, 2))
        tk.Label(resultados, text="ARQUIVOS ENCONTRADOS", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        lista_frame = tk.Frame(resultados, bg=PANEL)
        lista_frame.pack(fill="x", pady=(6, 0))
        self.lista = tk.Listbox(lista_frame, height=3, bg=PANEL, fg=TEXT, selectbackground=ACCENT, selectforeground="white", relief="flat", borderwidth=0, font=("Segoe UI", 10), activestyle="none")
        self.lista.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        self.lista.bind("<Double-Button-1>", lambda e: self._abrir_arquivo())
        tk.Button(lista_frame, text="Abrir selecionado", bg=PANEL_2, fg=TEXT, relief="flat", cursor="hand2", command=self._abrir_arquivo, padx=12, pady=8).pack(side="right", padx=9)

        area = tk.Frame(self.root, bg=BG)
        area.pack(fill="x", padx=24, pady=(12, 20))
        atalhos = tk.Frame(area, bg=BG)
        atalhos.pack(fill="x", pady=(0, 10))
        for titulo, comando in [ ("Calculadora", "abra a calculadora"), ("Bloco de notas", "abra o bloco de notas"), ("Meu currículo", "procure meu currículo"), ("Spotify", "abra o Spotify") ]:
            tk.Button(atalhos, text=titulo, bg=PANEL_2, fg=TEXT, relief="flat", cursor="hand2", activebackground="#3a4255", activeforeground="white", padx=12, pady=7, command=lambda c=comando: self._enviar(c)).pack(side="left", padx=(0, 8))
        entrada = tk.Frame(area, bg=PANEL)
        entrada.pack(fill="x")
        self.campo = tk.Entry(entrada, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, font=("Segoe UI", 12))
        self.campo.pack(side="left", fill="x", expand=True, padx=(15, 10), pady=14)
        self.campo.bind("<Return>", lambda e: self._enviar())
        self.botao = tk.Button(entrada, text="Enviar  ➜", bg=ACCENT, fg="#fff", relief="flat", activebackground="#7161d1", activeforeground="white", cursor="hand2", padx=20, pady=11, font=("Segoe UI", 10, "bold"), command=self._enviar)
        self.botao.pack(side="right", padx=8, pady=7)
        self.botao_voz = tk.Button(entrada, text="🎙 Falar", bg="#334358", fg="white", relief="flat", activebackground="#47617a", activeforeground="white", cursor="hand2", padx=14, pady=11, font=("Segoe UI", 10, "bold"), command=self._alternar_voz)
        self.botao_voz.pack(side="right", padx=3, pady=7)
        self.root.bind("<Control-Shift-space>", lambda e: self._alternar_voz())
        self._mensagem("Assistente", "Olá! Escreva ou use 🎙 Falar. Posso abrir aplicativos do Menu Iniciar, procurar arquivos, criar pastas e conversar com IA local. Pressione o microfone para iniciar e novamente para parar. Atalho: Ctrl+Shift+Espaço.")
        self.campo.focus_set()

    def _alternar_voz(self):
        if self.escutando:
            self._parar_voz()
            return
        if self.trabalhando:
            return
        try:
            from voz_local import VozLocal
            if self.voz is None:
                self.voz = VozLocal()
            self.voz.iniciar()
            self.escutando = True
            self.botao_voz.configure(text="■ Parar", bg="#a44d6a")
            self.status.set("● Gravando... fale agora")
            self.tempo_voz = self.root.after(12000, self._parar_voz)
        except Exception as exc:
            self._mensagem("Assistente", str(exc), erro=True)

    def _parar_voz(self):
        if not self.escutando:
            return
        self.escutando = False
        if self.tempo_voz is not None:
            self.root.after_cancel(self.tempo_voz)
            self.tempo_voz = None
        self.botao_voz.configure(text="🎙 Falar", bg="#334358", state="disabled")
        try:
            audio = self.voz.parar()
        except Exception as exc:
            self.botao_voz.configure(state="normal")
            self._mensagem("Assistente", str(exc), erro=True)
            return
        self.status.set("● Transcrevendo voz localmente... (primeiro uso pode baixar o modelo)")
        def worker():
            try:
                texto = self.voz.transcrever(audio)
                self.fila.put(('voz_texto', texto))
            except Exception as exc:
                self.fila.put(('voz_erro', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _mensagem(self, origem, texto, erro=False):
        self.chat.configure(state="normal")
        self.chat.insert("end", origem + "\n", "voce" if origem == "Você" else "ia")
        self.chat.insert("end", str(texto) + "\n\n", "erro" if erro else "corpo")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _ocupado(self, ocupado):
        self.trabalhando = ocupado
        self.botao.configure(state="disabled" if ocupado else "normal")

    def _verificar_modelos(self):
        def worker():
            try:
                dados = http_json("/api/tags", timeout=8)
                nomes = [m.get("name", "") for m in dados.get("models", []) if m.get("name")]
                self.fila.put(("modelos", nomes))
            except Exception as exc:
                self.fila.put(("status_erro", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _enviar(self, texto=None):
        if self.trabalhando:
            return
        if texto is None:
            texto = self.campo.get().strip()
        if not texto:
            return
        self.campo.delete(0, "end")
        self._mensagem("Você", texto)
        self._ocupado(True)
        self.status.set("Processando...")
        modelo = self.modelo.get()
        hist = list(self.historico)
        def worker():
            try:
                dados = comando_direto(texto)
                if dados is None:
                    dados = classificar_por_ia(texto, modelo)
                if dados.get("acao") == "responder":
                    resposta = conversar(texto, modelo, hist)
                    self.fila.put(("resposta", (texto, resposta)))
                elif dados.get("acao") == "buscar_arquivo":
                    arquivos = buscar_arquivos(str(dados.get("consulta", "")), normalizar(dados.get("pasta") or "todas"))
                    self.fila.put(("arquivos", arquivos))
                else:
                    self.fila.put(("acao", dados))
            except Exception as exc:
                self.fila.put(("erro", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _executar_acao(self, dados):
        acao = dados.get("acao")
        if acao == "abrir_programa":
            programa = normalizar(dados.get("programa", ""))
            # A IA fornece só nome; nunca shell ou caminho arbitrário.
            if not programa or re.search(r'[\\/:\x00-\x1f]', programa):
                raise ValueError("Nome de programa inválido.")
            achado = localizar_app(programa)
            if not achado:
                raise ValueError(f"Não encontrei '{programa}' no Menu Iniciar. O aplicativo está instalado?")
            nome, atalho, exato = achado
            if not exato and not messagebox.askyesno("Confirmar aplicativo", f"Você pediu: {programa}\n\nEncontrado um nome parecido: {nome}\n\nAbrir este aplicativo?"):
                self._mensagem("Assistente", "Abertura cancelada.")
                return
            if nome == "navegador":
                webbrowser.open("https://www.google.com/")
            elif nome in PROGRAMAS:
                subprocess.Popen([PROGRAMAS[nome]], shell=False)
            else:
                os.startfile(str(atalho))
            self._mensagem("Assistente", f"Solicitei ao Windows para abrir: {nome}.")
        elif acao == "abrir_pasta":
            local = normalizar(dados.get("pasta") or "")
            pastas = pastas_usuario()
            if local not in pastas:
                raise ValueError("Pasta não autorizada. Use Documentos, Downloads ou Área de Trabalho.")
            os.startfile(str(pastas[local]))
            self._mensagem("Assistente", f"Solicitei abertura da pasta: {pastas[local]}")
        elif acao == "criar_pasta":
            nome = dados.get("nome", "")
            local = normalizar(dados.get("pasta") or "")
            pastas = pastas_usuario()
            if local not in pastas:
                raise ValueError("Escolha Documentos, Downloads ou Área de Trabalho.")
            if not nome_seguro(nome):
                raise ValueError("Nome de pasta inválido ou inseguro.")
            destino = pastas[local] / nome
            if destino.exists():
                self._mensagem("Assistente", f"A pasta já existe: {destino}")
                return
            if messagebox.askyesno("Confirmar criação", f"Criar a pasta?\n\n{destino}"):
                destino.mkdir(exist_ok=False)
                self._mensagem("Assistente", f"Pasta criada!\n{destino}")
            else:
                self._mensagem("Assistente", "Criação de pasta cancelada.")
        else:
            raise ValueError("Ação não suportada.")

    def _mostrar_arquivos(self, arquivos):
        self.arquivos = arquivos
        self.lista.delete(0, "end")
        if not arquivos:
            self._mensagem("Assistente", "Não encontrei arquivos com esse nome nas pastas pessoais pesquisadas.")
            return
        for p in arquivos:
            self.lista.insert("end", f"{p.name}     •     {p.parent}")
        self.lista.selection_set(0)
        self._mensagem("Assistente", f"Encontrei {len(arquivos)} arquivo(s). Selecione um na lista abaixo e clique em 'Abrir selecionado'.")

    def _abrir_arquivo(self):
        escolha = self.lista.curselection()
        if not escolha or not self.arquivos:
            self._mensagem("Assistente", "Selecione um arquivo na lista primeiro.")
            return
        caminho = self.arquivos[escolha[0]]
        if caminho.suffix.lower() not in EXTENSOES:
            self._mensagem("Assistente", "Este tipo de arquivo não pode ser aberto automaticamente.", erro=True)
            return
        if not caminho.is_file() or caminho.is_symlink():
            self._mensagem("Assistente", "Esse arquivo não está mais disponível.", erro=True)
            return
        if messagebox.askyesno("Abrir arquivo", f"Abrir este arquivo com o programa padrão do Windows?\n\n{caminho}"):
            try:
                os.startfile(str(caminho))  # Windows: aplicativo padrao da extensao
                self._mensagem("Assistente", f"Solicitei a abertura de: {caminho.name}")
            except OSError as exc:
                self._mensagem("Assistente", f"Não foi possível abrir o arquivo: {exc}", erro=True)

    def _processar_fila(self):
        try:
            while True:
                evento, dado = self.fila.get_nowait()
                if evento == "voz_texto":
                    self.botao_voz.configure(state="normal")
                    if dado:
                        self._mensagem("Assistente", "Ouvi: " + dado)
                        self._enviar(dado)
                    else:
                        self.status.set("● Não reconheci a fala")
                        self._mensagem("Assistente", "Não entendi o áudio. Tente novamente falando mais perto do microfone.")
                elif evento == "voz_erro":
                    self.botao_voz.configure(state="normal")
                    self.status.set("● Falha no reconhecimento de voz")
                    self._mensagem("Assistente", dado, erro=True)
                elif evento == "modelos":
                    if dado:
                        self.selector["values"] = dado
                        if self.modelo.get() not in dado:
                            preferidos = ("qwen3:4b-instruct", "qwen3:8b", "qwen3.5:4b", "qwen2.5:1.5b")
                            self.modelo.set(next((m for m in preferidos if m in dado), dado[0]))
                        self.status.set("● Ollama conectado")
                        self.status_label.configure(fg=GREEN)
                    else:
                        self.status.set("Sem modelos locais: instale um modelo no Ollama")
                        self.status_label.configure(fg=RED)
                elif evento == "status_erro":
                    self.status.set("● Ollama desconectado")
                    self.status_label.configure(fg=RED)
                elif evento == "resposta":
                    pergunta, resposta = dado
                    self._mensagem("Assistente", resposta)
                    self.historico.extend([{"role": "user", "content": pergunta}, {"role": "assistant", "content": resposta}])
                    self.historico = self.historico[-12:]
                    self._ocupado(False)
                    self.status.set("● Ollama conectado")
                elif evento == "arquivos":
                    self._mostrar_arquivos(dado)
                    self._ocupado(False)
                    self.status.set("● Pronto")
                elif evento == "acao":
                    try:
                        self._executar_acao(dado)
                    except Exception as exc:
                        self._mensagem("Assistente", f"Não consegui executar: {exc}", erro=True)
                    self._ocupado(False)
                    self.status.set("● Pronto")
                elif evento == "erro":
                    self._mensagem("Assistente", dado, erro=True)
                    self._ocupado(False)
                    self.status.set("● Verifique a conexão e o modelo")
        except queue.Empty:
            pass
        self.root.after(90, self._processar_fila)


def main():
    if os.name != "nt":
        raise SystemExit("Este aplicativo foi criado para Windows 10/11.")
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT)
    Interface(root)
    root.mainloop()


if __name__ == "__main__":
    main()
