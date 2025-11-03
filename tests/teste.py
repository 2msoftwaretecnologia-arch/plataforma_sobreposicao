# -*- coding: utf-8 -*-
import pandas as pd

# === 1. Caminho do arquivo CSV ===
caminho_csv = "csvvv/conversao_imoveis.csv"  # altere o caminho conforme seu arquivo

# === 2. Ler o arquivo CSV ===
try:
    # Separa por vírgula, usa codificação UTF-8
    df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
    print("✅ Arquivo CSV carregado com sucesso!\n")
except FileNotFoundError:
    print(f"❌ Arquivo não encontrado: {caminho_csv}")
    exit()
except Exception as e:
    print(f"❌ Erro ao ler o CSV: {e}")
    exit()

# === 3. Exibir informações gerais ===
print("📋 Informações do DataFrame:")
print(df.info(), "\n")

print("🔹 Nome das colunas:")
print(df.columns.tolist(), "\n")

# print("🔸 Primeiras 5 linhas:")
# print(df.head(), "\n")

print(f"📊 Total de linhas: {df.shape[0]}, Total de colunas: {df.shape[1]}\n")

# # === 4. Exemplo de acesso a colunas e linhas ===
# if len(df.columns) >= 2:
#     print("🔍 Exemplo de acesso a uma coluna:")
#     print(df[df.columns[0]].head(), "\n")



# === 5. Filtros de exemplo (ajuste conforme suas colunas) ===
if 'cod_tema' in df.columns:
    #filtro_palmas = df[df['municipio'] == 'Palmas']
    print("🏙️ print da colunas cod_tema:")
    print(df['cod_tema'], "\n")

# if 'area' in df.columns:
#     filtro_area = df[df['area'] > 100]
#     print("🌾 Registros com área maior que 100:")
#     print(filtro_area.head(), "\n")

