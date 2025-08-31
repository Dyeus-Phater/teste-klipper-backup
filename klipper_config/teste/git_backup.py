# Klipper Git Backup - Componente para Moonraker (Versão Automatizada)
# Descrição: Monitora arquivos específicos e realiza backup automático para um
# repositório Git remoto (GitHub/GitLab) usando um token de acesso.

import subprocess
import os
import logging
import shlex
from urllib.parse import urlparse, urlunparse

class GitBackup:
    def __init__(self, config):
        self.server = config.get_server()
        # CORREÇÃO: Usa um método mais compatível para encontrar o diretório de configuração.
        main_config = config.get_main_config()
        config_dir = os.path.dirname(main_config.get_config_path())
        self.config_path = os.path.normpath(os.path.expanduser(config_dir))
        
        # Carrega as configurações do moonraker.conf
        self.is_enabled = config.getboolean('enabled', False)
        self.remote_url = config.get('remote_url', None)
        self.github_token = config.get('github_token', None)
        self.watched_files = [f.strip() for f in config.get('watched_files', 'printer.cfg').split(',')]
        self.commit_message = config.get('commit_message', 'Auto-backup: {filename} modificado')
        self.branch_name = config.get('branch', 'main')

        if not self.is_enabled:
            logging.info("GitBackup está desabilitado na configuração.")
            return

        logging.info(f"Plugin GitBackup inicializado. Monitorando: {', '.join(self.watched_files)}")
        
        try:
            self._validate_config()
            self._check_git_installed()
            self._initialize_repo()
            self._setup_remote()
            # Registra o handler para o evento de salvamento de arquivo
            self.server.register_event_handler("file_manager:file_saved", self._on_file_saved)
        except Exception as e:
            logging.error(f"Erro fatal na inicialização do GitBackup: {e}")
            # Desabilita o plugin se a inicialização falhar
            self.is_enabled = False

    def _validate_config(self):
        if not self.remote_url or not self.github_token:
            raise Exception("A 'remote_url' e o 'github_token' são obrigatórios no moonraker.conf")

    def _check_git_installed(self):
        try:
            self._run_git_command("git --version")
        except Exception:
            raise Exception("Comando 'git' não encontrado. Por favor, instale o git para usar o plugin.")

    def _run_git_command(self, command, suppress_errors=False):
        try:
            args = shlex.split(command)
            process = subprocess.run(
                args, cwd=self.config_path, capture_output=True, text=True, check=not suppress_errors
            )
            if process.returncode != 0 and not suppress_errors:
                 raise Exception(f"Erro Git: {process.stderr.strip()}")
            return process.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.error(f"Erro ao executar '{command}': {e.stderr}")
            if not suppress_errors:
                raise e
        return None

    def _initialize_repo(self):
        if os.path.isdir(os.path.join(self.config_path, '.git')):
            logging.info("Repositório Git já existe.")
            return
        
        logging.info("Inicializando novo repositório Git...")
        self._run_git_command("git init")
        self._run_git_command(f"git checkout -b {self.branch_name}")
        self._run_git_command('git config user.name "Klipper Backup Plugin"')
        self._run_git_command('git config user.email "backup@klipper.local"')
        
        # Adiciona apenas os arquivos monitorados ao primeiro commit
        for filename in self.watched_files:
            if os.path.exists(os.path.join(self.config_path, filename)):
                self._run_git_command(f"git add {shlex.quote(filename)}")
        
        self._run_git_command('git commit -m "Commit inicial: Arquivos de configuração monitorados"')
        logging.info("Repositório Git inicializado com sucesso.")

    def _setup_remote(self):
        logging.info("Configurando repositório remoto...")
        parsed_url = urlparse(self.remote_url)
        # Insere o token na URL: https://<token>@github.com/user/repo.git
        url_with_token = urlunparse(
            (parsed_url.scheme, f'{self.github_token}@{parsed_url.netloc}', parsed_url.path, '', '', '')
        )
        
        # Remove o remote 'origin' se ele já existir, para evitar erros
        self._run_git_command("git remote remove origin", suppress_errors=True)
        self._run_git_command(f"git remote add origin {shlex.quote(url_with_token)}")
        logging.info("Repositório remoto configurado com sucesso.")

    async def _on_file_saved(self, filepath):
        if not self.is_enabled:
            return

        filename = os.path.basename(filepath)
        
        if filename in self.watched_files:
            logging.info(f"Arquivo monitorado '{filename}' foi salvo. Iniciando backup...")
            try:
                # Adiciona o arquivo específico
                self._run_git_command(f"git add {shlex.quote(filepath)}")
                
                # Verifica se há algo para commitar
                status = self._run_git_command("git status --porcelain")
                if not status:
                    logging.info("Nenhuma modificação real detectada. Backup cancelado.")
                    return

                # Realiza o commit
                commit_msg = self.commit_message.format(filename=filename)
                self._run_git_command(f"git commit -m {shlex.quote(commit_msg)}")
                
                # Envia para o repositório remoto
                self._run_git_command(f"git push origin {self.branch_name}")
                
                logging.info(f"Backup de '{filename}' realizado com sucesso!")
            except Exception as e:
                logging.error(f"Falha ao fazer backup de '{filename}': {e}")


def load_component(config):
    return GitBackup(config)

