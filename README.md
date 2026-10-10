# ClipFlow — edição portátil para Windows

Essa versão prepara um **executável para Windows x64** que inclui o Python necessário,
FFmpeg, FFprobe e Deno dentro de um ZIP portátil. Depois de compilado, no computador
onde será usado basta extrair o ZIP e abrir `ClipFlow/ClipFlow.exe` — sem instalações
separadas de Python, FFmpeg ou Deno.

**O ZIP deste projeto contém o código e o processo de compilação, não o `.exe` já pronto.**
O `.exe` é gerado numa máquina Windows pelo GitHub Actions (online) ou pelo script
local (que exige ferramentas apenas na máquina de compilação).

## Sem instalar nada no seu computador: compilar online usando GitHub

1. Crie um repositório no [GitHub](https://github.com/new), por exemplo `clipflow-portable`.
2. Extraia este ZIP no computador e carregue **todos os arquivos e subpastas** para
   a raiz do repositório, preservando **`.github/workflows/build-windows.yml`**.
   O arquivo `.github` pode estar oculto dependendo da configuração do Windows.
3. No repositório, abra **Actions → Gerar ClipFlow Portable para Windows → Run workflow**.
   O fluxo também pode executar automaticamente após o primeiro envio para `main`.
4. Quando terminar, abra a execução → seção **Artifacts** →
   **ClipFlow-Windows-Portable**. Baixe e extraia o ZIP de artifact baixado;
   dentro dele está `ClipFlow-Windows-Portable.zip`, que contém a pasta do programa.
5. Extraia o ZIP final e execute **`ClipFlow/ClipFlow.exe`**.
   O ClipFlow abre no navegador e mantém uma janela de controle. Feche essa janela
   para encerrar o servidor local.

> Se o repositório foi criado com uma branch padrão diferente de `main`, utilize
> `Run workflow` após configurar uma branch `main`, ou ajuste a lista de branches
> no arquivo de workflow.

### No computador de compilação (opcional)

No Windows x64 com Python 3.11–3.13 instalado, dentro da pasta do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

O programa final ficará em `dist/ClipFlow/ClipFlow.exe`. A máquina que vai **usar**
o programa não precisa ter essas ferramentas de compilação.

## Funcionamento

- Você informa um link individual do YouTube para conteúdo próprio ou autorizado.
- O ClipFlow analisa o vídeo e oferece MP3 (bitrate de codificação) e MP4
  (resoluções retornadas pelo serviço).
- O servidor é acessível apenas em `127.0.0.1` e abre o navegador automaticamente.
- Arquivos temporários ficam em `%LOCALAPPDATA%\ClipFlow\downloads_temp` e são
  eliminados após serem enviados ao navegador, ou na limpeza por expiração.
- O aplicativo não requer hospedagem nem instalação das ferramentas Python,
  FFmpeg ou Deno no computador de uso.
- Continua sendo necessária **conexão com a internet** para analisar e baixar mídia.

## Limitações importantes

- **Não foi gerado nem testado um executável do Windows neste ambiente Linux.**
  Os testes de código podem passar, mas a compilação precisa acontecer em Windows.
- Antivírus/SmartScreen podem alertar sobre executáveis gerados sem assinatura
  digital; nunca desative as proteções do Windows indiscriminadamente.
- Mudanças no YouTube podem exigir atualizar o `yt-dlp` **e** `yt-dlp-ejs`
  conjuntamente; veja [guia EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
- Vídeos restritos, privados, com DRM, ao vivo ou que exigem login não são suportados.
- A seleção MP3 define a taxa de saída, não melhora o áudio original.
- Use somente para vídeos próprios ou cuja transferência/conversão sejam permitidas,
  respeitando os termos de cada plataforma e direitos dos autores.
- A distribuição pública de binários FFmpeg e Deno pode impor obrigações de
  licenciamento. Verifique as licenças de terceiros se for redistribuir seu app.

## Arquivos

- `server.py`: API FastAPI e processamento.
- `static/`: interface do site.
- `desktop.py`: inicia o programa portátil e abre o navegador.
- `scripts/build_windows.ps1`: baixa binários oficiais e empacota com PyInstaller.
- `.github/workflows/build-windows.yml`: compila online no Windows pelo GitHub.
- `requirements.txt`: dependências Python de compilação.

## Links de referência

- [PyInstaller](https://pyinstaller.org/en/stable/usage.html)
- [FFmpeg Windows builds](https://www.gyan.dev/ffmpeg/builds/)
- [Deno releases](https://github.com/denoland/deno/releases)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
