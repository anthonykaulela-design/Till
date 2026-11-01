import mysql.connector

def connect_db(self):
    return mysql.connector.connect(
        host="gateway01.eu-central-1.prod.aws.tidbcloud.com",          # Change to your remote MySQL server IP if hosted remotely
        user="3ELby3yHuXnNY9H.root",               # Your MySQL username
        password="lGTvpwXvCpuqB99y",  # Your MySQL password
        database="legal_saas"  # Ensure this database is created in MySQL beforehand
    )
