from webapps.database.db_factory import db_connect


class connectionFactory:
    def __init__(self) -> None:
        pass

    def CreateMSSqlConnection(self):
        try:
            return db_connect("sqlserver")
        except Exception as e:
            print(f"\n?嗡??秤: {str(e)}\n")
