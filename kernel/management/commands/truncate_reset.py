from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Apaga todos os registros de uma tabela e reseta o ID para 0'

    def add_arguments(self, parser):
        parser.add_argument('--table', required=True, help='Nome da tabela')
        parser.add_argument('--schema', required=False, help='Schema da tabela')
        parser.add_argument('--id-column', default='id', help='Coluna ID')
        parser.add_argument('--cascade', action='store_true', help='Usar TRUNCATE CASCADE')
        parser.add_argument('--start', type=int, default=0, help='Valor inicial desejado para a sequência (default: 0)')

    def handle(self, *args, **options):
        table = options['table']
        schema = options.get('schema')
        id_column = options['id_column']
        cascade = options['cascade']
        start = options['start']

        if not table:
            raise CommandError('Informe --table')

        if schema:
            qualified = f"{schema}.{table}"
            qn_table = f"{connection.ops.quote_name(schema)}.{connection.ops.quote_name(table)}"
        else:
            qualified = table
            qn_table = connection.ops.quote_name(table)

        sql_truncate = f"TRUNCATE TABLE {qn_table}{' CASCADE' if cascade else ''};"

        if start is None or start < 0:
            raise CommandError('--start deve ser um inteiro >= 0')

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql_truncate)
                cursor.execute('SELECT pg_get_serial_sequence(%s, %s)', [qualified, id_column])
                row = cursor.fetchone()
                seq = row[0] if row else None
                if not seq:
                    raise CommandError('Sequência não encontrada para a coluna informada')

                # Extrai schema e nome da sequência
                # Ex.: public.tb_area_sigef_id_seq
                if '.' in seq:
                    seq_schema, seq_name = seq.split('.', 1)
                else:
                    # Sem schema explícito, usa o informado (se houver)
                    seq_schema = schema or 'public'
                    seq_name = seq

                qn_seq = f"{connection.ops.quote_name(seq_schema)}.{connection.ops.quote_name(seq_name)}"

                # Garante que o MINVALUE da sequência suporta o valor inicial
                # Tenta ler de pg_sequences (PostgreSQL >= 10) e faz fallback para information_schema
                min_value = None
                try:
                    cursor.execute(
                        'SELECT min_value FROM pg_sequences WHERE schemaname=%s AND sequencename=%s',
                        [seq_schema, seq_name],
                    )
                    r = cursor.fetchone()
                    min_value = r[0] if r else None
                except Exception:
                    pass

                if min_value is None:
                    try:
                        cursor.execute(
                            'SELECT minimum_value FROM information_schema.sequences WHERE sequence_schema=%s AND sequence_name=%s',
                            [seq_schema, seq_name],
                        )
                        r = cursor.fetchone()
                        min_value = r[0] if r else None
                    except Exception:
                        min_value = None

                if min_value is not None and min_value > start:
                    cursor.execute(f'ALTER SEQUENCE {qn_seq} MINVALUE %s', [start])

                # Reinicia a sequência com o valor desejado
                cursor.execute(f'ALTER SEQUENCE {qn_seq} RESTART WITH %s', [start])

        self.stdout.write(self.style.SUCCESS(f'Tabela truncada e sequência reiniciada com {start}'))
