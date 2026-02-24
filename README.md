# EPWin MDB → MySQL Migrator

Ferramenta standalone para converter qualquer banco de dados **EPWin** (Bio-Logic) dos formatos `.mdb` (EPWinData.mdb + BLPatients.mdb) para **MySQL**.

Funciona com Docker ou com MySQL já instalado. Preserva toda a hierarquia de dados: pacientes → sessões → exames, com todos os canais/bancos por exame.

---

## Requisitos

- **Python** 3.10+
- **mdbtools** instalado no sistema (para ler os .mdb):
  - macOS: `brew install mdbtools`
  - Ubuntu/Debian: `sudo apt install mdbtools`
- **Docker** (opcional, para subir MySQL automaticamente)

```bash
pip install -r requirements.txt
```

---

## Uso rápido

### Com Docker (recomendado)

Sobe o MySQL automaticamente, aplica o schema e migra:

```bash
python migrate.py "caminho/para/EPWinData.mdb" "caminho/para/BLPatients.mdb" --docker
```

### MySQL já rodando

```bash
# Usando config.ini
cp config.example.ini config.ini
python migrate.py "caminho/para/EPWinData.mdb" "caminho/para/BLPatients.mdb" --config config.ini

# Ou passando credenciais diretamente
python migrate.py "caminho/para/EPWinData.mdb" "caminho/para/BLPatients.mdb" \
  --host localhost --user root --password epwin
```

---

## Listar bancos disponíveis

Para descobrir quais pares de .mdb existem em uma pasta:

```bash
python migrate.py --scan "caminho/para/pasta/com/bancos"
```

Exemplo de saída:
```
  [1] bancoDados_P300quaseOK_AEP_proximo/
       EPWinData.mdb  → .../EPWinData.mdb
       BLPatients.mdb → .../BLPatients.mdb

  [2] bancoDandosVEMP_OK/
       EPWinData.mdb  → .../EPWinData.mdb
       BLPatients.mdb → .../BLPatients.mdb
```

---

## Opções completas

```
positional:
  epwin_mdb          Caminho para EPWinData.mdb
  blpatients_mdb     Caminho para BLPatients.mdb

conexão:
  --config FILE      Arquivo .ini com [mysql] (default: config.ini)
  --host HOST        Servidor MySQL (default: localhost)
  --port PORT        Porta (default: 3306)
  --user USER        Usuário (default: root)
  --password PASS    Senha (default: epwin)
  --database DB      Banco de dados (default: epwin)

comportamento:
  --docker           Subir MySQL via docker compose antes de migrar
  --schema-only      Apenas aplicar schema.sql, sem migrar dados
  --no-truncate      Não limpar tabelas antes de inserir (modo append)
  --schema FILE      Caminho alternativo para schema.sql
  --scan DIR         Listar pares MDB disponíveis em um diretório
```

---

## Configuração MySQL (`config.ini`)

```bash
cp config.example.ini config.ini
```

```ini
[mysql]
host = localhost
port = 3306
user = root
password = epwin
database = epwin
```

---

## Docker

```bash
# Subir MySQL
docker compose up -d mysql

# Parar
docker compose down

# Remover dados (volume)
docker compose down -v
```

O container se chama `epwin-migrator-mysql` e expõe a porta `3306`.

---

## Estrutura do projeto

```
EPWinMigrator/
├── migrate.py          # CLI principal
├── schema.sql          # Schema MySQL (tabelas)
├── docker-compose.yml  # MySQL via Docker
├── config.example.ini  # Template de configuração
├── requirements.txt
└── src/
    ├── mdb_reader.py   # Lê EPWinData.mdb + BLPatients.mdb via mdbtools
    └── mysql_writer.py # Grava os dados no MySQL
```

---

## Schema MySQL

| Tabela               | Conteúdo |
|----------------------|----------|
| `patients`           | Dados de pacientes (BLPatients.mdb) |
| `sessions`           | Sessões agrupadas por data |
| `records`            | Exames/records com blob de dados (EPWinData.mdb) |
| `ep_data`            | Metadados por canal/banco (averages, rejected, filtros, dc_offset) |
| `stimulus_data`      | Orelha, estímulo, taxa, intensidade, delay |
| `amplifier_calibration` | Calibração uV/count por record |

---

## Queries úteis após migração

```sql
-- Contar exames por tipo
SELECT test_type_name, COUNT(*) AS total
FROM records
GROUP BY test_type_name
ORDER BY total DESC;

-- Listar pacientes
SELECT patient_id, first_name, last_name, birthdate, sex
FROM patients
ORDER BY last_name, first_name;

-- Exames de um paciente com estímulo
SELECT r.test_type_name, r.start_time, s.ear, s.stimulus, s.stim_rate, s.stim_intensity
FROM records r
JOIN sessions ss ON r.session_id = ss.id
JOIN patients p ON ss.patient_id = p.id
LEFT JOIN stimulus_data s ON r.record_id = s.record_id
WHERE p.patient_id = 'ID_DO_PACIENTE'
ORDER BY r.start_time;

-- Canais e bancos disponíveis por record
SELECT record_id, channel_number, bank_number, averages, rejected
FROM ep_data
WHERE record_id = 'SEU_RECORD_ID'
ORDER BY channel_number, bank_number;
```

---

## Licença

Conforme o projeto EPWinReader / SonorIA.
