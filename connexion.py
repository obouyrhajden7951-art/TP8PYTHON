"""
connexion.py - TP 8 : Gestion de contexte avancée, Exercice 2

  - ConnectionManager : simule une connexion (connexion / déconnexion tracées)
  - executer_tache / simuler_erreur : composition avec ExitStack
  - Logger : journal avec horodatage automatique (extension)
  - connecter_plusieurs : plusieurs connexions à la fois (extension)
"""

from contextlib import ExitStack, contextmanager
from datetime import datetime


# ======================================================================
# PARTIE 1 : ConnectionManager
# ======================================================================
class ConnectionManager:
    def __init__(self, service_name, sortie=print, echec_connexion=False):
        self.service_name = service_name
        self.connecte = False
        # 'sortie' : fonction qui reçoit les messages (print par défaut).
        # On peut la remplacer pour récupérer les messages dans un test.
        self._sortie = sortie
        # Permet de simuler un serveur injoignable
        self._echec_connexion = echec_connexion

    def __enter__(self):
        if self._echec_connexion:
            # Si __enter__ lève une exception, __exit__ n'est PAS appelé
            # (la ressource n'a jamais été ouverte).
            raise ConnectionError(f"Impossible de joindre {self.service_name}")
        self.connecte = True
        self._sortie(f"[{datetime.now()}] Connexion à {self.service_name} établie.")
        return self  # permet d'écrire : with ConnectionManager(...) as conn

    def __exit__(self, exc_type, exc_value, traceback):
        # Déconnexion TOUJOURS effectuée, avec ou sans erreur
        self.connecte = False
        self._sortie(f"[{datetime.now()}] Déconnexion de {self.service_name}.")
        if exc_type:
            self._sortie(f"Erreur détectée : {exc_type.__name__} — {exc_value}")
        # False : on signale l'erreur mais on ne l'étouffe pas
        return False

    def executer(self, commande):
        """Simule l'envoi d'une commande (impossible si déconnecté)."""
        if not self.connecte:
            raise ConnectionError(f"Pas de connexion à {self.service_name}")
        return f"{self.service_name} a exécuté : {commande}"


# ======================================================================
# PARTIE 2 : composition avec ExitStack
# ======================================================================
def executer_tache(chemin_log, service, sortie=print, ouvreur=open):
    """Ouvre un fichier de log ET une connexion, écrit une trace, ferme tout."""
    with ExitStack() as stack:
        # Ordre d'ouverture : log d'abord, connexion ensuite.
        log = stack.enter_context(ouvreur(chemin_log, "a", encoding="utf-8"))
        conn = stack.enter_context(ConnectionManager(service, sortie))
        # NB : "\n" doit être écrit avec l'échappement dans la chaîne
        # (un vrai saut de ligne dans un f-string simple est une erreur de syntaxe).
        log.write(f"[{datetime.now()}] Tâche effectuée sur {conn.service_name}\n")
    # À la sortie, ordre INVERSE : déconnexion d'abord, puis fermeture du log.
    return conn


# ======================================================================
# PARTIE 3 : simulation d'erreur
# ======================================================================
def simuler_erreur(chemin_log, service, sortie=print, ouvreur=open):
    """Lève volontairement une exception dans le bloc with."""
    with ExitStack() as stack:
        stack.enter_context(ouvreur(chemin_log, "a", encoding="utf-8"))
        stack.enter_context(ConnectionManager(service, sortie))
        # Les DEUX ressources seront fermées proprement malgré cette erreur
        raise RuntimeError("Erreur de traitement")


# ======================================================================
# EXTENSION 1 : Logger avec horodatage automatique
# ======================================================================
class Logger:
    """Fichier de log : chaque message reçoit automatiquement un timestamp."""

    def __init__(self, chemin, ouvreur=open):
        self.chemin = chemin
        self._ouvreur = ouvreur
        self._f = None

    def __enter__(self):
        self._f = self._ouvreur(self.chemin, "a", encoding="utf-8")
        return self

    def ecrire(self, message):
        self._f.write(f"[{datetime.now()}] {message}\n")

    def __exit__(self, exc_type, exc_value, traceback):
        self._f.close()
        return False

    @property
    def ferme(self):
        return self._f is not None and self._f.closed


# ======================================================================
# EXTENSION 2 : plusieurs connexions
# ======================================================================
@contextmanager
def connecter_plusieurs(services, sortie=print):
    """Ouvre une connexion par service ; toutes sont fermées à la sortie."""
    with ExitStack() as stack:
        yield [stack.enter_context(ConnectionManager(s, sortie)) for s in services]


if __name__ == "__main__":
    executer_tache("log.txt", "Serveur X")
    try:
        simuler_erreur("log.txt", "Base Y")
    except RuntimeError as e:
        print("Exception reçue après nettoyage :", e)