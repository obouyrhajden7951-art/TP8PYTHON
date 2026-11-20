"""
contexte_fichiers.py - TP 8 : Gestion de contexte avancée, Exercice 1

Trois façons de gérer une ressource (un fichier) avec 'with' :
  1) une classe avec __enter__ / __exit__      -> TempFileWriter
  2) un générateur décoré @contextmanager      -> temp_file
  3) plusieurs ressources avec ExitStack       -> ouvrir_plusieurs

Idée centrale : 'with' garantit que le nettoyage (fermer, supprimer...)
est exécuté, QUE le bloc se termine normalement OU par une exception.
"""

from contextlib import contextmanager, ExitStack
from pathlib import Path


def _noter(log, message):
    """Appelle la fonction de log si elle existe (log=None : rien ne se passe)."""
    if log is not None:
        log(message)


# ======================================================================
# PARTIE 1 : classe avec __enter__ et __exit__
# ======================================================================
class TempFileWriter:
    """Fichier temporaire : créé à l'entrée du with, supprimé à la sortie."""

    def __init__(self, filepath="temp.txt", encoding="utf-8", log=None):
        # Le chemin est un paramètre (valeur par défaut = celle de l'énoncé),
        # ce qui permet de tester sans polluer le dossier courant.
        self.filepath = Path(filepath)
        self.encoding = encoding
        self._log = log  # fonction facultative : log("message")

    def __enter__(self):
        # Appelée au début du bloc with. Ce qu'on RETOURNE ici est
        # ce qui est affecté après "as" :  with TempFileWriter() as f
        self.f = self.filepath.open("w", encoding=self.encoding)
        _noter(self._log, f"Ouverture de {self.filepath}")
        return self.f

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Appelée à la fin du bloc, avec ou sans exception.
        # exc_type / exc_val / exc_tb = infos sur l'exception (None si aucune).
        try:
            self.f.close()
        finally:
            # try/finally : même si close() échoue, on supprime le fichier.
            # missing_ok=True : pas d'erreur si le fichier a déjà disparu.
            self.filepath.unlink(missing_ok=True)
            _noter(self._log, f"Fermeture et suppression de {self.filepath}")
        # Retourner False (ou None) = ne PAS avaler l'exception :
        # elle continue de se propager après le nettoyage.
        return False


# ======================================================================
# PARTIE 2 : @contextmanager (même comportement, version générateur)
# ======================================================================
@contextmanager
def temp_file(filepath="temp.txt", encoding="utf-8", log=None):
    chemin = Path(filepath)
    # Le code AVANT yield joue le rôle de __enter__.
    # On ouvre AVANT le try : si open() échoue, il n'y a rien à nettoyer.
    f = chemin.open("w", encoding=encoding)
    _noter(log, f"Ouverture de {chemin}")
    try:
        yield f  # la valeur après "as" ; le bloc with s'exécute ici
    finally:
        # Le code du finally joue le rôle de __exit__ : il s'exécute toujours,
        # et si le bloc a levé une exception, elle est relancée ensuite.
        try:
            f.close()
        finally:
            chemin.unlink(missing_ok=True)
            _noter(log, f"Fermeture et suppression de {chemin}")


# ======================================================================
# PARTIE 3 : plusieurs ressources avec ExitStack
# ======================================================================
@contextmanager
def ouvrir_plusieurs(chemins, mode="w", encoding="utf-8", ouvreur=open):
    """Ouvre tous les fichiers ; les ferme tous, même en cas d'erreur.

    'ouvreur' permet de remplacer open() (pratique pour les tests).
    """
    # ExitStack = une pile de "choses à fermer". Chaque enter_context()
    # ouvre une ressource ET l'empile. À la sortie, tout est fermé en
    # ordre INVERSE (dernier ouvert, premier fermé).
    # Si la 3e ouverture échoue, les 2 premiers fichiers sont fermés quand même :
    # c'est ce qu'une simple liste + boucle ne garantit pas.
    with ExitStack() as pile:
        fichiers = [
            pile.enter_context(ouvreur(chemin, mode, encoding=encoding))
            for chemin in chemins
        ]
        yield fichiers


# ======================================================================
# EXTENSION : reprise sur exception
# ======================================================================
class ResultatErreur:
    """Boîte qui contiendra l'exception capturée (None s'il n'y en a pas)."""
    erreur = None


@contextmanager
def tolerer(*types_erreurs):
    """Capture les exceptions des types indiqués au lieu de les propager."""
    resultat = ResultatErreur()
    try:
        yield resultat
    except types_erreurs as e:  # n'attrape QUE les types demandés
        resultat.erreur = e     # le programme continue après le with


if __name__ == "__main__":
    with TempFileWriter(log=print) as f:
        f.write("Contenu temporaire\n")
    with temp_file(log=print) as f:
        f.write("Autre test\n")
    with ouvrir_plusieurs(["a.txt", "b.txt", "c.txt"]) as fichiers:
        for fichier in fichiers:
            fichier.write("test\n")
    with tolerer(ValueError) as r:
        int("abc")
    print("Erreur capturée :", r.erreur)