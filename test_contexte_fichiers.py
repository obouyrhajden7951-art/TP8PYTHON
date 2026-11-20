"""
test_contexte_fichiers.py - Tests de contexte_fichiers.py
Lancer avec :  python -m unittest test_contexte_fichiers -v
"""

import os
import tempfile
import unittest
from pathlib import Path

from contexte_fichiers import TempFileWriter, temp_file, ouvrir_plusieurs, tolerer


def espion(ouverts):
    """Fabrique un faux open() qui mémorise les fichiers ouverts."""
    def ouvrir(*args, **kwargs):
        f = open(*args, **kwargs)
        ouverts.append(f)
        return f
    return ouvrir


class BaseTest(unittest.TestCase):
    def setUp(self):
        # Dossier temporaire créé pour chaque test et supprimé ensuite
        self._dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        self.dossier = Path(self._dossier.name)


class TestFichierTemporaire(BaseTest):
    """Les deux versions (classe et générateur) doivent se comporter pareil."""

    def test_deux_versions_identiques(self):
        for fabrique in (TempFileWriter, temp_file):
            with self.subTest(fabrique=fabrique.__name__):
                chemin = self.dossier / "t.txt"
                with fabrique(chemin) as f:
                    f.write("Contenu temporaire\n")
                    f.flush()
                    # Pendant le with : le fichier existe et contient le texte
                    self.assertTrue(chemin.exists())
                    self.assertEqual(chemin.read_text(encoding="utf-8"), "Contenu temporaire\n")
                # Après le with : fermé ET supprimé
                self.assertTrue(f.closed)
                self.assertFalse(chemin.exists())

    def test_nettoyage_si_exception(self):
        for fabrique in (TempFileWriter, temp_file):
            with self.subTest(fabrique=fabrique.__name__):
                chemin = self.dossier / "t.txt"
                with self.assertRaises(RuntimeError):  # l'exception n'est pas avalée
                    with fabrique(chemin) as f:
                        f.write("x")
                        raise RuntimeError("boum")
                self.assertTrue(f.closed)
                self.assertFalse(chemin.exists())

    def test_fichier_deja_supprime(self):
        # Si le fichier disparaît pendant le bloc, pas d'erreur à la sortie
        for fabrique in (TempFileWriter, temp_file):
            with self.subTest(fabrique=fabrique.__name__):
                chemin = self.dossier / "t.txt"
                with fabrique(chemin) as f:
                    f.close()
                    chemin.unlink()

    def test_echec_ouverture(self):
        # Dossier inexistant : l'erreur d'open() est propagée telle quelle
        for fabrique in (TempFileWriter, temp_file):
            with self.subTest(fabrique=fabrique.__name__):
                with self.assertRaises(FileNotFoundError):
                    with fabrique(self.dossier / "absent" / "t.txt"):
                        pass

    def test_log_ouverture_et_fermeture(self):
        for fabrique in (TempFileWriter, temp_file):
            with self.subTest(fabrique=fabrique.__name__):
                messages = []
                with fabrique(self.dossier / "t.txt", log=messages.append):
                    pass
                self.assertEqual(len(messages), 2)
                self.assertIn("Ouverture", messages[0])
                self.assertIn("Fermeture", messages[1])

    def test_log_present_meme_en_cas_d_erreur(self):
        messages = []
        with self.assertRaises(ValueError):
            with TempFileWriter(self.dossier / "t.txt", log=messages.append):
                raise ValueError()
        self.assertIn("Fermeture", messages[-1])

    def test_accents(self):
        chemin = self.dossier / "t.txt"
        with TempFileWriter(chemin) as f:
            f.write("été\n")
            f.flush()
            self.assertEqual(chemin.read_text(encoding="utf-8"), "été\n")

    def test_chemin_par_defaut(self):
        self.assertEqual(TempFileWriter().filepath, Path("temp.txt"))


class TestOuvrirPlusieurs(BaseTest):
    def chemins(self, *noms):
        return [str(self.dossier / n) for n in noms]

    def test_ecriture_dans_tous_les_fichiers(self):
        chemins = self.chemins("a.txt", "b.txt", "c.txt")
        with ouvrir_plusieurs(chemins) as fichiers:
            self.assertEqual(len(fichiers), 3)
            for f in fichiers:
                f.write("test\n")
        for chemin in chemins:
            self.assertEqual(Path(chemin).read_text(), "test\n")

    def test_tous_fermes_apres_with(self):
        with ouvrir_plusieurs(self.chemins("a", "b")) as fichiers:
            pass
        self.assertTrue(all(f.closed for f in fichiers))

    def test_tous_fermes_si_exception_dans_le_bloc(self):
        with self.assertRaises(RuntimeError):
            with ouvrir_plusieurs(self.chemins("a", "b", "c")) as fichiers:
                raise RuntimeError("boum")
        self.assertTrue(all(f.closed for f in fichiers))

    def test_fichiers_deja_ouverts_fermes_si_une_ouverture_echoue(self):
        # La 3e ouverture échoue (dossier inexistant) : les 2 premiers
        # doivent être fermés malgré tout.
        ouverts = []
        chemins = self.chemins("a.txt", "b.txt") + [str(self.dossier / "absent" / "c.txt")]
        with self.assertRaises(FileNotFoundError):
            with ouvrir_plusieurs(chemins, ouvreur=espion(ouverts)):
                self.fail("Le bloc ne doit pas s'exécuter")
        self.assertEqual(len(ouverts), 2)
        self.assertTrue(all(f.closed for f in ouverts))

    def test_liste_vide(self):
        with ouvrir_plusieurs([]) as fichiers:
            self.assertEqual(fichiers, [])

    def test_mode_lecture(self):
        chemin = self.dossier / "a.txt"
        chemin.write_text("bonjour")
        with ouvrir_plusieurs([chemin], mode="r") as (f,):
            self.assertEqual(f.read(), "bonjour")


class TestTolerer(unittest.TestCase):
    def test_capture_l_erreur_demandee(self):
        with tolerer(ValueError) as r:
            int("abc")
        self.assertIsInstance(r.erreur, ValueError)

    def test_le_programme_continue_apres(self):
        with tolerer(ValueError):
            int("abc")
        self.assertTrue(True)  # on arrive ici : l'exception a été absorbée

    def test_autre_type_est_propage(self):
        with self.assertRaises(KeyError):
            with tolerer(ValueError):
                {}["x"]

    def test_sans_erreur(self):
        with tolerer(ValueError) as r:
            pass
        self.assertIsNone(r.erreur)

    def test_plusieurs_types(self):
        with tolerer(ValueError, KeyError) as r:
            {}["x"]
        self.assertIsInstance(r.erreur, KeyError)


if __name__ == "__main__":
    unittest.main()