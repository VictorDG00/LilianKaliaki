"""Sobe os containers Postgres (Infra/docker-compose.yml) e aplica as migrations do Alembic."""

import subprocess
import sys
import time

COMPOSE_FILE = "Infra/docker-compose.yml"
WAIT_TIMEOUT_S = 30


def run(descricao, cmd):
    print(f"-> {descricao}...")
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        print(f"\n[ERRO] Falhou em: {descricao}")
        print(f"Comando: {' '.join(cmd)}")
        print(resultado.stderr.strip() or resultado.stdout.strip())
        sys.exit(1)
    print("   ok")
    return resultado


def aguardar_postgres():
    descricao = "Aguardando Postgres (db) aceitar conexões"
    print(f"-> {descricao}...")
    inicio = time.time()
    ultimo_erro = ""
    while time.time() - inicio < WAIT_TIMEOUT_S:
        resultado = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", "db", "pg_isready", "-U", "postgres"],
            capture_output=True,
            text=True,
        )
        if resultado.returncode == 0:
            print("   ok")
            return
        ultimo_erro = resultado.stderr.strip() or resultado.stdout.strip()
        time.sleep(1)
    print(f"\n[ERRO] Falhou em: {descricao}")
    print(f"Timeout de {WAIT_TIMEOUT_S}s excedido. Último erro: {ultimo_erro}")
    sys.exit(1)


def main():
    run("Subindo containers Docker (db + db_test)", ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"])
    aguardar_postgres()
    run("Aplicando migrations (alembic upgrade head)", ["alembic", "upgrade", "head"])
    print("\nAmbiente pronto: containers no ar e schema atualizado.")


if __name__ == "__main__":
    main()
