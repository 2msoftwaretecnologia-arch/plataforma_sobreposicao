# Plataforma de Sobreposição Ambiental

Aplicação Django para análise geoespacial de imóveis rurais. Ela recebe uma área de interesse por número do CAR, arquivo ZIP com shapefile ou PDFs do CAR, cruza essa geometria com várias bases ambientais/fundiárias e apresenta os resultados em tela, mapa, relatório e arquivos para download.

## O que a aplicação faz

- Consulta registros do SICAR/CAR cadastrados no banco.
- Recebe shapefile compactado em ZIP e extrai a geometria da propriedade.
- Lê PDFs de Recibo e Demonstrativo do CAR usando `pdfplumber`.
- Calcula sobreposição entre a área analisada e bases como zoneamento, fitoecologia, APAs, terras indígenas, quilombolas, veredas, unidades de conservação, municípios, SIGEF, assentamentos, SNIC, MapBiomas, embargos IBAMA, PRODES, IPUCA e rodovias.
- Calcula áreas em hectares usando geometrias convertidas para SIRGAS 2000 / UTM 22S (`EPSG:31982`).
- Exibe resultados por base, polígonos no mapa, tabelas, relatório para impressão e downloads em KML/SHP.
- Importa bases geográficas a partir de arquivos ZIP cadastrados no painel administrativo.
- Executa importações também por Celery/RabbitMQ.

## Stack principal

- Python 3.11
- Django 5.2
- GeoDjango/PostGIS
- GeoPandas, Shapely, PyProj, GDAL/GEOS
- Celery com RabbitMQ
- django-celery-results e django-celery-beat
- django-leaflet para visualização geográfica no admin
- pdfplumber para extração de texto de PDFs
- uWSGI e Nginx para execução em Docker

## Fluxo resumido

1. O usuário acessa a tela inicial em `/`.
2. Em `/analysis/`, informa um CAR, envia um ZIP com shapefile ou envia PDF de recibo/demonstrativo.
3. A aplicação obtém uma geometria válida (`GEOSGeometry`, SRID 4674).
4. `SearchAll` cria um alvo geográfico e executa `OverlapPipeline`.
5. `OverlapService` consulta cada camada geográfica e calcula as interseções.
6. Os formatadores transformam cada interseção em dados amigáveis para a interface.
7. `FinalResultBuilder` monta o resultado final para tela, mapa, relatório e sessão.
8. O usuário visualiza os resultados em `/results/`, imprime relatório em `/report/print/` ou baixa KML/SHP.

## Como rodar com Docker

Crie um arquivo `.env` na raiz com as variáveis necessárias e execute:

```bash
docker compose up --build
```

Serviços criados:

- `rabbitmq`: broker Celery, com painel em `http://localhost:15672`.
- `app`: Django rodando via uWSGI em `http://localhost:8000`.
- `worker`: worker Celery.
- `beat`: agendador Celery Beat.
- `nginx`: proxy na porta `80`, servindo estáticos e mídia.

## Como rodar localmente

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --no-input
python manage.py runserver
```

Para tarefas assíncronas, rode também RabbitMQ e:

```bash
celery -A kernel worker -l info
celery -A kernel beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Variáveis de ambiente

O projeto lê configurações pelo `python-decouple`. O `.env` não deve ser versionado.

Variáveis esperadas:

- `SECRET_KEY`: chave secreta do Django.
- `DEBUG`: controla modo de desenvolvimento/produção.
- `DB_ENGINE`: engine do banco, normalmente PostGIS.
- `DB_NAME`: nome do banco.
- `DB_USER`: usuário do banco.
- `DB_PASSWORD`: senha do banco.
- `HOST_BD`: host do banco.
- `PORT_BD`: porta do banco.
- `GDAL_LIBRARY_PATH`: caminho da biblioteca GDAL.
- `GEOS_LIBRARY_PATH`: caminho da biblioteca GEOS.
- `CELERY_BROKER_URL`: URL do RabbitMQ.
- `CELERY_RESULT_BACKEND`: backend de resultado Celery.
- `PLANET_API_KEY`: chave opcional para tiles Planet.
- `PLANET_BASEMAP_MOSAIC`: mosaico opcional do basemap Planet.
- `STATIC_VERSION`: versão/cache-busting de arquivos estáticos.

## Comandos úteis de importação

Os comandos importam dados dos ZIPs cadastrados no painel `FileManagement`.

```bash
python manage.py import_sicar_area
python manage.py import_zoning_area
python manage.py import_phyto_ecology_area
python manage.py import_protection_area
python manage.py import_indigenous_area
python manage.py import_quilobolas_area
python manage.py import_paths_areas
python manage.py import_coservations_unit_area
python manage.py import_municial_boundaries
python manage.py import_sigef_area
python manage.py import_ruralsettlement_area
python manage.py import_snic_total_Area
python manage.py deforestation_import
python manage.py embargoe_import
python manage.py prodes_import
python manage.py Highways_area
python manage.py ipuca_area
```

Também existe:

```bash
python manage.py truncate_reset <tabela>
python clean_pycache.py
```

## Estrutura do projeto

### Raiz

- `.gitignore`: define arquivos ignorados pelo Git, como `.env`, `venv/`, caches, banco local, mídia, `staticfiles/` e logs gerados.
- `.env`: arquivo local de configuração e segredos. Não deve ir para o Git.
- `.DS_Store`: metadado gerado pelo macOS. Não faz parte da aplicação.
- `README.md`: documentação do projeto.
- `manage.py`: CLI padrão do Django.
- `requirements.txt`: dependências Python.
- `Dockerfile`: imagem da aplicação com Python, GDAL, GEOS, PROJ, dependências e uWSGI.
- `docker-compose.yml`: orquestra app, RabbitMQ, worker, beat e Nginx.
- `nginx.docker.conf`: proxy Nginx para a aplicação e arquivos estáticos/mídia.
- `uwsgi.ini`: configuração do uWSGI.
- `clean_pycache.py`: script para remover `__pycache__`, `.pyc` e `.pyo`.
- `car_data.json`: arquivo gerado em runtime com dados de análise extraídos de PDF/CAR.
- `final_output.json`: arquivo gerado em runtime com o último resultado completo da análise.
- `performance_log.json`: arquivo gerado em runtime com tempos da análise.
- `venv/`: ambiente virtual local.
- `staticfiles/`: saída do `collectstatic`.
- `tests/`: arquivos HTML/CSS usados como referência/teste visual de relatório.

### `kernel/`

Projeto Django principal.

- `settings.py`: configura apps, banco, arquivos estáticos, mídia, Celery, GDAL/GEOS, autenticação e variáveis de ambiente.
- `urls.py`: registra as rotas principais: admin, autenticação e análise.
- `wsgi.py` e `asgi.py`: pontos de entrada para servidores WSGI/ASGI.
- `celery.py`: inicializa o Celery e descobre tarefas dos apps.
- `models.py`: define `GeoBaseModel`, classe abstrata usada por quase todas as bases geográficas.
- `utils.py`: funções auxiliares para área, extração de geometria, localização de cidade/UF, parsing decimal e reset de tabelas.
- `context_processors.py`: injeta `STATIC_VERSION` nos templates.
- `apps.py`: configuração do app `kernel`.
- `service/geometry_processing_service.py`: converte WKT em `GeometryField`, corrige SRID e calcula área em m²/ha.
- `service/database_maintenance_service.py`: executa `TRUNCATE` e reinicia sequência de IDs.
- `service/city_state_locator_service.py`: usa Nominatim/OpenStreetMap para localizar município e UF a partir de uma geometria.
- `service/abstract/base_formatter.py`: contrato base para formatadores de resultados.
- `management/commands/truncate_reset.py`: comando administrativo para limpar tabela e reiniciar sequência.

### `analysis/`

App da experiência principal de análise.

- `urls.py`: rotas de upload, resultados, relatório, downloads e termos.
- `views.py`: controla upload de ZIP/PDF, busca por CAR, análise de coordenadas, resultados, relatório e exportação KML/SHP.
- `services/view_services/zip_upload_service.py`: lê o ZIP enviado e retorna um `GeoDataFrame`.
- `services/analyze_coordinates/search_for_car.py`: localiza um registro SICAR e executa análise pela geometria dele.
- `services/analyze_coordinates/search_all.py`: serviço de alto nível que executa toda a análise de sobreposição.
- `services/analyze_coordinates/overlap/geometry_target.py`: representa a geometria alvo e calcula sua área.
- `services/analyze_coordinates/overlap/overlap_service.py`: calcula interseções espaciais entre o alvo e uma camada.
- `services/analyze_coordinates/overlap/pipeline.py`: percorre todas as camadas registradas e aplica formatadores.
- `services/analyze_coordinates/overlap/formatter_register.py`: registra todos os modelos analisados e seus formatadores.
- `services/analyze_coordinates/overlap/final_result_builder.py`: monta a resposta final consumida pela interface.
- `templates/analysis/*.html`: páginas de upload, resultados, relatório, loader, termos e landing page.
- `templates/analysis/components/`: componentes reutilizados nos resultados.
- `templates/analysis/components/tables/`: tabelas específicas por base.
- `templates/analysis/components/base/`: componentes específicos para tipos de resultado.
- `static/analysis/css/*.css`: estilos das telas, relatório e termos.
- `static/analysis/js/maps.js`: lógica do mapa.
- `static/analysis/js/upload.js`: interações da tela de upload.
- `static/analysis/images/icon_page.svg`: ícone usado na interface.
- `admin.py`, `apps.py`, `__init__.py`: arquivos padrão do app Django.

### `authentication/`

Login e logout.

- `urls.py`: rotas `/accounts/` e `/accounts/logout/`.
- `views.py`: autentica usuário, cria sessão e encerra sessão.
- `templates/login/login.html`: tela de login.
- `static/authentication/css/login.css`: estilo da tela de login.
- `models.py`, `admin.py`, `apps.py`, `tests.py`, `migrations/`: estrutura padrão do app.

### `control_panel/`

Painel administrativo para cadastrar os arquivos ZIP usados nas importações.

- `models.py`: modelo `FileManagement`, com um campo de arquivo para cada base.
- `admin.py`: registra `FileManagement` no admin e limita a criação a um único registro.
- `signals.py`: remove arquivos antigos quando um ZIP é substituído.
- `utils.py`: obtém o registro de gerenciamento de arquivos.
- `migrations/`: histórico das alterações de schema do painel.
- `apps.py`, `__init__.py`: configuração padrão do app.

### `car_system/`

Base SICAR/CAR.

- `models.py`: modelo `SicarRecord`, com número CAR, status, data de atualização e dados geográficos herdados.
- `utils.py`: helper para consultar registros SICAR.
- `admin.py`: registro no admin com visualização Leaflet.
- `tasks/sicar_importer.py`: importador da base SICAR a partir do ZIP cadastrado.
- `tasks/celery_tasks.py`: task Celery para importar SICAR.
- `management/commands/import_sicar_area.py`: comando Django para importação manual.
- `services/formatter/sicar_formatter.py`: formata interseções SICAR para a tela.
- `migrations/`: evolução do schema da base SICAR.

### `environmental_layers/`

Bases ambientais gerais.

- `models.py`: modelos `ZoningArea`, `PhytoecologyArea`, `EnvironmentalProtectionArea` e `IndigenousArea`.
- `constants.py`: constantes usadas pelo domínio ambiental.
- `admin.py`: registros no admin com mapa Leaflet.
- `tasks/*_importer.py`: importadores de zoneamento, fitoecologia, proteção ambiental e terras indígenas.
- `tasks/celery_tasks.py`: tasks Celery dessas importações.
- `management/commands/import_*.py`: comandos Django para importação manual.
- `services/formatter/*.py`: formatadores dessas camadas para a análise.
- `migrations/`: histórico das tabelas ambientais.

### `naturatins/`

Bases relacionadas a Naturatins/territórios locais.

- `models.py`: modelos `Quilombolas`, `Paths`, `ConservationUnits` e `MunicipalBoundaries`.
- `admin.py`: registros no admin com Leaflet.
- `tasks/*_importer.py`: importadores de quilombolas, veredas, unidades de conservação e municípios.
- `tasks/celery_tasks.py`: tasks Celery dessas importações.
- `management/commands/import_*.py`: comandos manuais.
- `services/formatter/*.py`: formatadores das camadas.
- `migrations/`: histórico do schema.

### `gov/`

Bases fundiárias/governamentais.

- `models.py`: modelos `Sigef`, `Ruralsettlement` e `SnicTotal`.
- `admin.py`: registros no admin.
- `tasks/*_importer.py`: importadores das três bases.
- `tasks/celery_tasks.py`: tasks Celery.
- `management/commands/import_*.py`: comandos manuais.
- `services/formatter/*.py`: formatadores para resultados.
- `migrations/`: histórico do schema.

### `deforestation_fires/`

Bases de desmatamento, embargos e PRODES.

- `models.py`: modelos `DeforestationMapbiomas`, `Embargoes` e `Prodes`.
- `constants.py`: constantes do domínio.
- `utils.py`: monta URL relacionada ao MapBiomas.
- `admin.py`: registros no admin.
- `tasks/*_importer.py`: importadores de MapBiomas, embargos e PRODES.
- `tasks/celery_tasks.py`: tasks Celery.
- `management/commands/deforestation_import.py`: importa desmatamento MapBiomas.
- `management/commands/embargoe_import.py`: importa embargos.
- `management/commands/prodes_import.py`: importa PRODES.
- `management/commands/convert.py`: comando auxiliar de conversão.
- `services/formatter/*.py`: formatadores das bases.
- `migrations/`: histórico do schema.

### `seplan/`

Bases IPUCA e rodovias.

- `models.py`: modelos `Highways` e `Ipuca`.
- `admin.py`: registros no admin.
- `views.py`: arquivo de views padrão, sem fluxo principal implementado.
- `tests.py`: teste simples de modelo.
- `tasks/Highways_importer.py` e `tasks/ipuca_importer.py`: importadores.
- `tasks/celery_tasks.py`: tasks Celery.
- `management/commands/Highways_area.py` e `ipuca_area.py`: comandos de importação.
- `services/formatter/Highways.py` e `ipuca.py`: formatadores.
- `migrations/`: histórico do schema.

### `doc_extractor/`

Extração e parsing de PDFs do CAR.

- `services/pdf_engine.py`: funções diretas para extrair texto de PDFs com `pdfplumber`.
- `services/parsers/constants.py`: enum dos tipos de documento.
- `services/parsers/context/extract_data_context.py`: coordena extrator e parser.
- `services/parsers/contract/*.py`: contratos abstratos para extratores e parsers.
- `services/parsers/factory/documents_parser_factory.py`: cria parser de Recibo ou Demonstrativo.
- `services/parsers/implement/extract_text/extract_pdf_plumber.py`: implementação de extração com `pdfplumber`.
- `services/parsers/implement/parcer_document/receipt_parser.py`: parser orientado a objeto para Recibo.
- `services/parsers/implement/parcer_document/statement_parser.py`: parser orientado a objeto para Demonstrativo.
- `services/parsers/database/receipt_info.py`: dataclass com campos extraídos do Recibo.
- `services/parsers/database/statement_info.py`: dataclass com campos extraídos do Demonstrativo.
- `services/parsers/recibo.py` e `demonstrativo.py`: funções antigas/auxiliares de parsing.
- `views.py`, `models.py`, `admin.py`, `tests.py`, `migrations/`: estrutura padrão do app.

## Padrões importantes do código

- Todos os modelos geográficos relevantes herdam de `GeoBaseModel`.
- O campo `geometry` guarda WKT textual.
- O campo `usable_geometry` guarda a geometria espacial usada nas consultas PostGIS.
- `area_m2` e `area_ha` são pré-calculados para acelerar a análise.
- Cada base tem um `Importer` para ler ZIP/shapefile, criar registros e processar geometria.
- Cada base tem um `Formatter` para transformar interseções em dados prontos para UI.
- `FormatterRegister` define quais bases entram na análise.
- `OverlapService` usa `usable_geometry__intersects` e `Intersection` para calcular sobreposições.
- `FinalResultBuilder` consolida resultados por base e prepara polígonos para o mapa.

## Arquivos gerados em execução

- `final_output.json`: última saída estruturada da análise.
- `performance_log.json`: tempos de processamento.
- `car_data.json`: dados extraídos/processados durante análise por documento.
- `media/`: uploads feitos pelo admin.
- `staticfiles/`: arquivos estáticos coletados.

Esses arquivos normalmente não devem ser usados como fonte permanente de dados; o banco é a fonte principal.
