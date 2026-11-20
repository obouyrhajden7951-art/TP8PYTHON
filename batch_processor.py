"""
batch_processor.py - TP 8 : Gestion de contexte avancée, Exercice 3

BatchProcessor : gestionnaire de contexte qui
  - ouvre un fichier CSV d'opérations (une par ligne)
  - traite chaque ligne (traitement simulé)
  - journalise débuts et fins dans un fichier journal.log
  - ferme TOUJOURS les deux fichiers, même en cas d'exception

Modules utilisés : contextlib, datetime, csv (comme demandé).
"""

import csv
from contextlib import ExitStack
from datetime import datetime


# ======================================================================
# EXCEPTIONS PERSONNALISÉES
# ======================================================================
# Elles permettent de distinguer clairement un problème de LECTURE
# d'un problème d'ÉCRITURE, au lieu d'un OSError générique.
class ErreurLecture(Exception):
    """Le fichier CSV ne peut pas être ouvert ou lu."""


class ErreurEcriture(Exception):
    """Le journal ne peut pas être ouvert ou écrit."""


# ======================================================================
# TRAITEMENT SIMULÉ PAR DÉFAUT
# ======================================================================
def operation_par_defaut(ligne):
    """Transformation simulée : assemble les champs et met en majuscules."""
    return "|".join(ligne).upper()


# ======================================================================
# GESTIONNAIRE DE CONTEXTE
# ======================================================================
class BatchProcessor:
    def __init__(self, chemin_csv, chemin_journal="journal.log",
                 continuer_sur_erreur=False, ouvreur=open):
        self.chemin_csv = chemin_csv
        self.chemin_journal = chemin_journal
        # True  : une ligne en échec est journalisée, on passe à la suivante
        # False : la 1re erreur arrête le traitement (l'exception se propage)
        self.continuer_sur_erreur = continuer_sur_erreur
        self._ouvreur = ouvreur  # remplaçable pour les tests

        self._stack = None
        self._fichier = None   # fichier CSV (lecture)
        self._journal = None   # fichier journal (écriture)
        self._handles = []     # tous les fichiers ouverts (pour 'fermes')
        self.traitees = 0
        self.erreurs = 0

    # ------------------------------------------------------------------
    # Entrée dans le bloc with
    # ------------------------------------------------------------------
    def __enter__(self):
        # ExitStack : si la 2e ouverture échoue, la 1re est fermée
        # automatiquement (c'est tout son intérêt).
        self._stack = ExitStack()
        self._handles = []
        self.traitees = self.erreurs = 0
        try:
            try:
                # newline="" est la valeur recommandée par le module csv
                self._fichier = self._stack.enter_context(
                    self._ouvreur(self.chemin_csv, newline="", encoding="utf-8"))
                self._handles.append(self._fichier)
            except OSError as e:  # FileNotFoundError, PermissionError...
                raise ErreurLecture(f"Impossible d'ouvrir '{self.chemin_csv}' : {e}") from e

            try:
                # "a" = ajout : on garde le journal des exécutions précédentes
                self._journal = self._stack.enter_context(
                    self._ouvreur(self.chemin_journal, "a", encoding="utf-8"))
                self._handles.append(self._journal)
            except OSError as e:
                raise ErreurEcriture(f"Impossible d'ouvrir '{self.chemin_journal}' : {e}") from e
        except BaseException:
            # __exit__ n'est PAS appelé quand __enter__ échoue : on ferme donc
            # nous-mêmes ce qui a déjà été ouvert, puis on relance l'erreur.
            self._stack.close()
            raise

        self._journaliser("Début du lot")
        return self

    # ------------------------------------------------------------------
    # Sortie du bloc with (avec ou sans exception)
    # ------------------------------------------------------------------
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._journaliser(
                    f"Fin du lot : {self.traitees} ligne(s) traitée(s), {self.erreurs} erreur(s)")
            else:
                self._journaliser(f"Lot interrompu : {exc_type.__name__}: {exc_val}")
        except ErreurEcriture:
            # Si une exception est DÉJÀ en cours, on ne la masque pas avec
            # une erreur de journal : l'erreur d'origine est plus importante.
            if exc_type is None:
                raise
        finally:
            # finally : la fermeture des fichiers a lieu quoi qu'il arrive
            self._stack.close()
        return False  # ne jamais avaler l'exception du bloc

    # ------------------------------------------------------------------
    # Outils internes
    # ------------------------------------------------------------------
    def _journaliser(self, message):
        """Écrit une ligne horodatée dans le journal (erreurs d'écriture gérées)."""
        try:
            self._journal.write(f"[{datetime.now()}] {message}\n")
            self._journal.flush()  # écrit sur disque tout de suite : rien n'est perdu si crash
        except (OSError, ValueError) as e:  # ValueError : fichier déjà fermé
            raise ErreurEcriture(f"Écriture dans le journal impossible : {e}") from e

    @property
    def fermes(self):
        """True si tous les fichiers ouverts par le gestionnaire sont fermés."""
        return bool(self._handles) and all(h.closed for h in self._handles)

    # ------------------------------------------------------------------
    # Traitement des lignes
    # ------------------------------------------------------------------
    def traiter(self, operation=None):
        """Traite chaque ligne du CSV ; retourne la liste des résultats."""
        if self._fichier is None:
            raise RuntimeError("traiter() doit être appelé dans un bloc with")
        operation = operation or operation_par_defaut
        resultats = []
        lecteur = csv.reader(self._fichier)

        while True:
            # On lit "à la main" pour isoler les erreurs de LECTURE
            # (octets illisibles, CSV malformé) des erreurs de TRAITEMENT.
            try:
                ligne = next(lecteur)
            except StopIteration:
                break  # fin du fichier
            except (UnicodeDecodeError, csv.Error, OSError) as e:
                raise ErreurLecture(f"Lecture impossible : {e}") from e

            if not ligne:  # ligne vide : ignorée
                continue
            numero = lecteur.line_num

            self._journaliser(f"Début traitement ligne {numero} : {ligne}")
            try:
                resultat = operation(ligne)
            except Exception as e:
                self.erreurs += 1
                self._journaliser(f"Échec ligne {numero} : {type(e).__name__}: {e}")
                if not self.continuer_sur_erreur:
                    raise  # on relance : le with va tout fermer proprement
                continue   # sinon on passe à la ligne suivante
            self.traitees += 1
            resultats.append(resultat)
            self._journaliser(f"Fin traitement ligne {numero}")
        return resultats


if __name__ == "__main__":
    # Prépare un petit CSV de démonstration
    with open("operations.csv", "w", encoding="utf-8", newline="") as f:
        f.write("addition,2,3\nmajuscule,bonjour\n\nafficher,fin\n")

    with BatchProcessor("operations.csv", "journal.log") as batch:
        for resultat in batch.traiter():
            print("Résultat :", resultat)
    print("Fichiers fermés :", batch.fermes)
    print(open("journal.log", encoding="utf-8").read())