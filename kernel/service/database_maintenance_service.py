from django.db import connection, transaction


class DatabaseMaintenanceService:
    def truncate_and_reset(self, table, schema=None, id_column='id', cascade=False, start=1):
        if start is None or start < 0:
            raise ValueError('start deve ser um inteiro >= 0')

        if schema:
            qualified = f"{schema}.{table}"
            qn_table = f"{connection.ops.quote_name(schema)}.{connection.ops.quote_name(table)}"
        else:
            qualified = table
            qn_table = connection.ops.quote_name(table)

        sql_truncate = f"TRUNCATE TABLE {qn_table}{' CASCADE' if cascade else ''};"

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql_truncate)
                cursor.execute('SELECT pg_get_serial_sequence(%s, %s)', [qualified, id_column])
                row = cursor.fetchone()
                seq = row[0] if row else None
                if not seq:
                    raise ValueError('Sequência não encontrada para a coluna informada')

                if '.' in seq:
                    seq_schema, seq_name = seq.split('.', 1)
                else:
                    seq_schema = schema or 'public'
                    seq_name = seq

                qn_seq = f"{connection.ops.quote_name(seq_schema)}.{connection.ops.quote_name(seq_name)}"

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

                cursor.execute(f'ALTER SEQUENCE {qn_seq} RESTART WITH %s', [start])

        return {
            'table': table,
            'schema': schema,
            'id_column': id_column,
            'cascade': cascade,
            'start': start,
        }
