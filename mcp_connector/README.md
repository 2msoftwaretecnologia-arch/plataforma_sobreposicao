# Conector MCP (Claude e ChatGPT)

Permite usar a plataforma conversando com o Claude (claude.ai, app desktop ou
celular) ou com o ChatGPT: o assistente faz as análises de sobreposição,
explica os resultados, redige relatórios, mostra o mapa e entrega os links de
KML/SHP. Mesmo desenho do conector do CRM Agropassos.

## Como funciona

```
Assistente (nuvem da Anthropic / OpenAI)
   │  1. descobre o OAuth:  GET /.well-known/oauth-protected-resource/mcp  → mcp
   │                        GET /.well-known/oauth-authorization-server    → app
   │  2. registra o cliente: POST /o/register/                             → app
   │  3. usuário entra na plataforma e autoriza: /o/authorize/             → app
   │  4. troca o código por token: POST /o/token/                          → app
   │  5. chama as ferramentas: POST /mcp  (Authorization: Bearer …)        → mcp
   └─ 6. o usuário abre os links de download: GET /conector/arquivos/…/    → app
```

- **app** (Django/uWSGI): login, tela "Permitir acesso?" e emissão de tokens
  (`django-oauth-toolkit`, PKCE obrigatório, escopo `analises`), e os links de
  download.
- **mcp** (`python manage.py run_mcp_server`, serviço `mcp` do
  `docker-compose.yml`, porta 8002): servidor MCP via Streamable HTTP. Valida
  o token, identifica o usuário e executa a ferramenta em nome dele.
- O nginx do compose encaminha `/mcp` e `/.well-known/oauth-protected-resource*`
  para o `mcp`, e o resto para o `app`.

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `analisar_car` | Cruza o imóvel do CAR com todas as bases |
| `analisar_coordenadas` | Coordenadas digitadas (uma por linha): 1 ponto acha o imóvel do SICAR que o contém; 3+ vértices formam o polígono |
| `analisar_geometria` | Conteúdo de um KML, GeoJSON ou WKT (ex.: arquivo anexado na conversa) |
| `analisar_parcela_sigef` | Cruza uma parcela do SIGEF com as bases |
| `localizar_ponto` | Município, CARs e parcelas SIGEF de uma coordenada, sem análise |
| `listar_analises` | Histórico do usuário (plataforma e assistente juntos) |
| `detalhes_analise` | Resumo de uma análise ou todos os itens/atributos de uma base |
| `relatorio_analise` | Conteúdo do relatório impresso: veredito, semáforo de perguntas, bases com ocorrência explicadas, Reserva Legal, vegetação e comparativo MapBiomas 2008 × atual |
| `mapa_analise` | Imagem do mapa (print) com o imóvel e as sobreposições, legenda e escala; padrão = bases de alerta/atenção, `todas`, ou uma base com cada item numa cor |
| `arquivos_analise` | Links de KML/SHP do imóvel, de cada base e de todas as sobreposições (KML com uma pasta colorida por base) e o PNG do mapa |

Cada análise feita pelo assistente entra no histórico do usuário como as da
tela; o `analise_id` é o id do histórico, e os links "resultado" e "relatório
para imprimir" abrem a análise na plataforma.

Exemplos de pedidos:
- "Analisa o CAR TO-1721000-… e me diz se tem algum problema."
- "Esse KML (anexo) sobrepõe alguma terra indígena ou embargo?"
- "Qual imóvel fica em -10.18, -48.33? Analisa ele."
- "Faz um relatório para o banco sobre a análise 116, com o mapa."
- "Me manda o KML das sobreposições do PRODES."
- "Mostra o mapa só com os CARs vizinhos que sobrepõem."

## Permissões e segurança

- Qualquer conta ativa pode conectar. As ferramentas usam só as bases
  liberadas para a conta (mesmas regras da tela, em
  `control_panel/access_service.py`), inclusive ao reabrir análises antigas.
- Cada chamada fica em **Admin → Consultas pelo assistente**
  (`tb_auditoria_mcp`), com usuário, ferramenta, argumentos e resultado.
- Desativar o usuário corta o acesso na hora.
- O registro de clientes OAuth só aceita os callbacks do Claude e do ChatGPT
  (`MCP_ALLOWED_REDIRECT_URIS`).
- Os links de download são assinados, valem 24 h (`MCP_FILE_LINK_MAX_AGE`) e
  abrem sem login: quem tiver o link baixa o arquivo. O arquivo é gerado na
  hora, com as bases que o dono do link pode ver naquele momento.

## Implantação (VPS 82.25.66.238)

O Claude e o ChatGPT só aceitam conectores em **HTTPS** com certificado
válido e acessíveis pela internet. Pelo IP puro (`http://82.25.66.238:8020`)
a conexão é recusada. Sem domínio, use o nome gratuito do sslip.io
`sobreposicao.82-25-66-238.sslip.io` (resolve para o IP da VPS).

1. **HTTPS no host.** Quem ocupa as portas 80/443 da VPS termina o TLS e
   repassa para `127.0.0.1:8020`:
   - Nginx do host: use `mcp_connector/deploy/nginx-host-sslip.conf` (os
     comandos de instalação e do certbot estão no topo do arquivo).
   - Caddy do CRM: acrescente um site `sobreposicao.82-25-66-238.sslip.io`
     com `reverse_proxy` para a porta 8020 do host (o container do Caddy
     precisa de `extra_hosts: ["host.docker.internal:host-gateway"]`).
2. **`.env` do servidor:**
   `MCP_PUBLIC_BASE_URL=https://sobreposicao.82-25-66-238.sslip.io`
3. **`docker-compose.override.yml` do servidor:** o serviço `mcp` precisa do
   mesmo banco do `app` e do `worker` (`HOST_BD: postgis`), como os blocos
   que já existem para eles.
4. **Deploy.** Há dependências novas (`requirements.txt`), então a imagem
   precisa ser reconstruída **antes** de recriar os containers; sem isso o
   `app`, o `worker` e o `beat` não sobem (falta o `oauth2_provider`):

   ```bash
   git pull
   docker compose build app worker
   docker compose up -d --no-deps --force-recreate app worker beat mcp
   docker compose exec -T nginx nginx -s reload
   ```

   As migrações (`oauth2_provider` e `mcp_connector`) rodam no `migrate` do
   `app`. Conferir: `https://sobreposicao.82-25-66-238.sslip.io/.well-known/oauth-protected-resource/mcp`
   deve devolver um JSON.

## Adicionar o conector

**Claude** (Pro/Max: *Configurações → Conectores → Adicionar conector
personalizado*; Team/Enterprise: um administrador adiciona em *Configurações
da organização → Conectores*): URL `https://sobreposicao.82-25-66-238.sslip.io/mcp`.
Ao clicar em **Conectar**, abre o login da plataforma e a tela "Permitir
acesso?". Os tokens valem 1 hora e são renovados sozinhos por até 30 dias.

**ChatGPT** (planos pagos): *Configurações → Apps e conectores → Configurações
avançadas → Modo desenvolvedor*; depois **Criar** conector com a mesma URL e
autenticação **OAuth**, deixando Client ID e Secret em branco (registro
dinâmico). Na conversa, selecione o conector no menu **+**. O ChatGPT pede
confirmação antes das ferramentas de análise, porque elas gravam no histórico.

## Desenvolvimento local

Com o túnel do banco aberto (ver README principal), em dois terminais:

```bash
.venv\Scripts\python.exe manage.py runserver
.venv\Scripts\python.exe manage.py run_mcp_server
```

Sem `MCP_PUBLIC_BASE_URL`, os metadados apontam para
`http://localhost:8000` (OAuth) e `http://localhost:8002/mcp` (MCP), e com
`DEBUG=True` o OAuth aceita callbacks em `localhost` (Claude Code e MCP
Inspector).

Token de desenvolvimento, sem passar pelo login (só com `DEBUG=True`):

```bash
.venv\Scripts\python.exe manage.py mcp_dev_token <usuario> --days 7
```

O comando imprime o `claude mcp add` pronto para colar no Claude Code. Para o
fluxo OAuth completo: `claude mcp add --transport http sobreposicao-dev
http://localhost:8002/mcp` e, no Claude Code, `/mcp` → **Authenticate**.

Para testar com o claude.ai sem publicar, exponha a máquina por um túnel HTTPS
(`cloudflared`, `ngrok`) que mande `/mcp` e `/.well-known/oauth-protected-resource*`
para a 8002 e o resto para a 8000, e defina `MCP_PUBLIC_BASE_URL` com a URL
do túnel.

Testes: `.venv\Scripts\python.exe manage.py test mcp_connector` (sem banco).
