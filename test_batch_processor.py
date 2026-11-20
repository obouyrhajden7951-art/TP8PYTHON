"""
test_batch_processor.py - Tests de batch_processor.py
Lancer avec :  python -m unittest test_batch_processor -v
"""

import os
import tempfile
import unittest
from pathlib import Path

from batch_processor import (
    BatchProcessor, ErreurLecture, ErreurEcriture, operation_par_defaut,
)


def espion(ouverts):
    """Faux open() qui mémorise chaque fichier ouvert."""
    def ouvrir(*args, **kwargs):
        f = open(*args, **kwargs)
        ouverts.append(f)
        return f
    return ouvrir


class FichierCasse:
    """Simule un disque plein : toute écriture échoue."""
    def write(self, texte):
        raise OSError("disque plein")

    def flush(self):
        raise OSError("disque plein")


class BaseTest(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        d = Path(self._dossier.name)
        self.csv = str(d / "operations.csv")
        self.journal = str(d / "journal.log")
        self.ecrire_csv("addition,2,3\nmajuscule,été\n\nafficher,fin\n")

    def ecrire_csv(self, texte):
        Path(self.csv).write_text(texte, encoding="utf-8", newline="")

    def lire_journal(self):
        return Path(self.journal).read_text(encoding="utf-8")


# ======================================================================
class TestTraitement(BaseTest):
    def test_resultats_par_defaut(self):
        with BatchProcessor(self.csv, self.journal) as b:
            resultats = b.traiter()
        # La ligne vide est ignorée ; les accents sont conservés
        self.assertEqual(resultats, ["ADDITION|2|3", "MAJUSCULE|ÉTÉ", "AFFICHER|FIN"])
        self.assertEqual((b.traitees, b.erreurs), (3, 0))

    def test_operation_personnalisee(self):
        with BatchProcessor(self.csv, self.journal) as b:
            resultats = b.traiter(lambda ligne: len(ligne))
        self.assertEqual(resultats, [3, 2, 2])

    def test_operation_par_defaut_directe(self):
        self.assertEqual(operation_par_defaut(["a", "b"]), "A|B")

    def test_csv_vide(self):
        self.ecrire_csv("")
        with BatchProcessor(self.csv, self.journal) as b:
            self.assertEqual(b.traiter(), [])

    def test_champ_entre_guillemets_avec_virgule(self):
        self.ecrire_csv('texte,"a, b"\n')
        with BatchProcessor(self.csv, self.journal) as b:
            self.assertEqual(b.traiter(lambda l: l), [["texte", "a, b"]])

    def test_traiter_hors_with(self):
        with self.assertRaises(RuntimeError):
            BatchProcessor(self.csv, self.journal).traiter()


# ======================================================================
class TestJournal(BaseTest):
    def test_contenu_du_journal(self):
        with BatchProcessor(self.csv, self.journal) as b:
            b.traiter()
        j = self.lire_journal()
        self.assertIn("Début du lot", j)
        self.assertIn("Début traitement ligne 1 : ['addition', '2', '3']", j)
        self.assertIn("Fin traitement ligne 1", j)
        self.assertIn("Fin traitement ligne 4", j)   # ligne 3 vide ignorée
        self.assertIn("Fin du lot : 3 ligne(s) traitée(s), 0 erreur(s)", j)

    def test_chaque_ligne_est_horodatee(self):
        with BatchProcessor(self.csv, self.journal) as b:
            b.traiter()
        for ligne in self.lire_journal().splitlines():
            self.assertRegex(ligne, r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\] ")

    def test_ordre_debut_puis_fin(self):
        with BatchProcessor(self.csv, self.journal) as b:
            b.traiter()
        lignes = self.lire_journal().splitlines()
        self.assertIn("Début du lot", lignes[0])
        self.assertIn("Fin du lot", lignes[-1])

    def test_journal_en_ajout(self):
        for _ in range(2):
            with BatchProcessor(self.csv, self.journal) as b:
                b.traiter()
        self.assertEqual(self.lire_journal().count("Début du lot"), 2)


# ======================================================================
class TestFermeture(BaseTest):
    def test_fichiers_fermes_apres_with(self):
        ouverts = []
        with BatchProcessor(self.csv, self.journal, ouvreur=espion(ouverts)) as b:
            self.assertFalse(b.fermes)   # ouverts pendant le bloc
            b.traiter()
        self.assertEqual(len(ouverts), 2)
        self.assertTrue(b.fermes)
        self.assertTrue(all(f.closed for f in ouverts))

    def test_fermes_si_exception_dans_le_bloc(self):
        ouverts = []
        with self.assertRaises(RuntimeError):
            with BatchProcessor(self.csv, self.journal, ouvreur=espion(ouverts)) as b:
                raise RuntimeError("boum")
        self.assertTrue(b.fermes)
        self.assertTrue(all(f.closed for f in ouverts))
        self.assertIn("Lot interrompu : RuntimeError: boum", self.lire_journal())

    def test_fermes_si_une_ligne_echoue(self):
        def operation(ligne):
            if ligne[0] == "majuscule":
                raise ValueError("ligne invalide")
            return ligne[0]

        ouverts = []
        with self.assertRaises(ValueError):
            with BatchProcessor(self.csv, self.journal, ouvreur=espion(ouverts)) as b:
                b.traiter(operation)
        self.assertTrue(all(f.closed for f in ouverts))
        j = self.lire_journal()
        self.assertIn("Échec ligne 2 : ValueError: ligne invalide", j)
        self.assertIn("Lot interrompu : ValueError", j)
        self.assertNotIn("Début traitement ligne 4", j)   # arrêté à la ligne 2

    def test_exception_non_avalee(self):
        # __exit__ retourne False : l'exception arrive bien à l'appelant
        with self.assertRaises(KeyError):
            with BatchProcessor(self.csv, self.journal):
                {}["x"]


# ======================================================================
class TestContinuerSurErreur(BaseTest):
    def operation(self, ligne):
        if ligne[0] == "majuscule":
            raise ValueError("invalide")
        return ligne[0]

    def test_continue_apres_une_erreur(self):
        with BatchProcessor(self.csv, self.journal, continuer_sur_erreur=True) as b:
            resultats = b.traiter(self.operation)
        self.assertEqual(resultats, ["addition", "afficher"])
        self.assertEqual((b.traitees, b.erreurs), (2, 1))
        self.assertIn("Fin du lot : 2 ligne(s) traitée(s), 1 erreur(s)", self.lire_journal())


# ======================================================================
class TestErreursLecture(BaseTest):
    def test_csv_introuvable(self):
        with self.assertRaises(ErreurLecture) as ctx:
            with BatchProcessor(self.csv + ".absent", self.journal):
                self.fail("Le bloc ne doit pas s'exécuter")
        self.assertIsInstance(ctx.exception.__cause__, FileNotFoundError)

    def test_csv_introuvable_ne_cree_pas_de_journal(self):
        with self.assertRaises(ErreurLecture):
            with BatchProcessor(self.csv + ".absent", self.journal):
                pass
        self.assertFalse(os.path.exists(self.journal))

    def test_csv_est_un_dossier(self):
        with self.assertRaises(ErreurLecture):
            with BatchProcessor(os.path.dirname(self.csv), self.journal):
                pass

    def test_octets_illisibles(self):
        Path(self.csv).write_bytes(b"ok,1\n\xff\xfe\xfa\n")
        ouverts = []
        with self.assertRaises(ErreurLecture):
            with BatchProcessor(self.csv, self.journal, ouvreur=espion(ouverts)) as b:
                b.traiter()
        self.assertTrue(all(f.closed for f in ouverts))   # fermés malgré l'erreur
        self.assertIn("Lot interrompu : ErreurLecture", self.lire_journal())


class TestErreursEcriture(BaseTest):
    def test_journal_inaccessible_ferme_le_csv(self):
        # Journal dans un dossier inexistant : le CSV (déjà ouvert) doit être fermé
        ouverts = []
        mauvais = os.path.join(os.path.dirname(self.journal), "absent", "j.log")
        with self.assertRaises(ErreurEcriture) as ctx:
            with BatchProcessor(self.csv, mauvais, ouvreur=espion(ouverts)):
                self.fail("Le bloc ne doit pas s'exécuter")
        self.assertIsInstance(ctx.exception.__cause__, FileNotFoundError)
        self.assertEqual(len(ouverts), 1)       # seul le CSV a pu être ouvert
        self.assertTrue(ouverts[0].closed)

    def test_ecriture_impossible_pendant_le_traitement(self):
        ouverts = []
        with self.assertRaises(ErreurEcriture):
            with BatchProcessor(self.csv, self.journal, ouvreur=espion(ouverts)) as b:
                b._journal = FichierCasse()     # le disque "tombe" en cours de route
                b.traiter()
        # Les vrais fichiers sont fermés quand même
        self.assertTrue(all(f.closed for f in ouverts))

    def test_ecriture_impossible_a_la_sortie(self):
        # Pas d'exception dans le bloc, mais la dernière écriture échoue :
        # l'erreur est signalée ET les fichiers sont fermés.
        ouverts = []
        with self.assertRaises(ErreurEcriture):
            with BatchProcessor(self.csv, self.journal, ouvreur=espion(ouverts)) as b:
                b._journal = FichierCasse()
        self.assertTrue(all(f.closed for f in ouverts))

    def test_erreur_d_origine_non_masquee(self):
        # Exception dans le bloc + journal cassé : c'est l'erreur d'origine qui remonte
        with self.assertRaises(RuntimeError):
            with BatchProcessor(self.csv, self.journal) as b:
                b._journal = FichierCasse()
                raise RuntimeError("erreur d'origine")


class TestReutilisation(BaseTest):
    def test_meme_objet_reutilisable(self):
        b = BatchProcessor(self.csv, self.journal)
        for _ in range(2):
            with b:
                self.assertEqual(len(b.traiter()), 3)
            self.assertTrue(b.fermes)
        self.assertEqual(self.lire_journal().count("Début du lot"), 2)

    def test_compteurs_remis_a_zero(self):
        b = BatchProcessor(self.csv, self.journal)
        with b:
            b.traiter()
        with b:
            self.assertEqual((b.traitees, b.erreurs), (0, 0))


if __name__ == "__main__":
    unittest.main()