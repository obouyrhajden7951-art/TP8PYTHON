"""
test_connexion.py - Tests de connexion.py
Lancer avec :  python -m unittest test_connexion -v
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from connexion import (
    ConnectionManager, executer_tache, simuler_erreur, Logger, connecter_plusieurs,
)


def espion(ouverts):
    def ouvrir(*args, **kwargs):
        f = open(*args, **kwargs)
        ouverts.append(f)
        return f
    return ouvrir


class BaseTest(unittest.TestCase):
    def setUp(self):
        self._dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        self.log = str(Path(self._dossier.name) / "log.txt")


class TestConnectionManager(unittest.TestCase):
    def test_connecte_dans_le_bloc_deconnecte_apres(self):
        conn = ConnectionManager("S", sortie=lambda m: None)
        self.assertFalse(conn.connecte)
        with conn as c:
            self.assertIs(c, conn)       # __enter__ retourne self
            self.assertTrue(c.connecte)
        self.assertFalse(conn.connecte)

    def test_messages_sans_erreur(self):
        messages = []
        with ConnectionManager("Serveur X", messages.append):
            pass
        self.assertEqual(len(messages), 2)
        self.assertRegex(messages[0], r"^\[\d{4}-\d{2}-\d{2} .*\] Connexion à Serveur X établie\.$")
        self.assertRegex(messages[1], r"Déconnexion de Serveur X\.$")

    def test_messages_avec_erreur(self):
        messages = []
        with self.assertRaises(ValueError):
            with ConnectionManager("S", messages.append):
                raise ValueError("oups")
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[2], "Erreur détectée : ValueError — oups")

    def test_deconnexion_meme_en_cas_d_erreur(self):
        conn = ConnectionManager("S", lambda m: None)
        with self.assertRaises(RuntimeError):
            with conn:
                raise RuntimeError()
        self.assertFalse(conn.connecte)

    def test_executer(self):
        with ConnectionManager("S", lambda m: None) as c:
            self.assertEqual(c.executer("ping"), "S a exécuté : ping")

    def test_executer_hors_connexion(self):
        conn = ConnectionManager("S", lambda m: None)
        with self.assertRaises(ConnectionError):
            conn.executer("ping")
        with conn:
            pass
        with self.assertRaises(ConnectionError):  # déjà déconnecté
            conn.executer("ping")

    def test_echec_de_connexion(self):
        messages = []
        conn = ConnectionManager("S", messages.append, echec_connexion=True)
        with self.assertRaises(ConnectionError):
            with conn:
                pass
        self.assertEqual(messages, [])  # ni connexion ni déconnexion tracées
        self.assertFalse(conn.connecte)

    def test_print_par_defaut(self):
        tampon = io.StringIO()
        with redirect_stdout(tampon):
            with ConnectionManager("S"):
                pass
        self.assertIn("Connexion à S établie", tampon.getvalue())


class TestExecuterTache(BaseTest):
    def test_ecrit_dans_le_log(self):
        executer_tache(self.log, "Serveur X", sortie=lambda m: None)
        texte = Path(self.log).read_text(encoding="utf-8")
        self.assertRegex(texte, r"Tâche effectuée sur Serveur X\n$")

    def test_log_en_ajout(self):
        # Mode "a" : les exécutions successives s'accumulent
        for _ in range(3):
            executer_tache(self.log, "X", sortie=lambda m: None)
        lignes = Path(self.log).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 3)

    def test_tout_ferme_apres(self):
        ouverts = []
        conn = executer_tache(self.log, "X", sortie=lambda m: None, ouvreur=espion(ouverts))
        self.assertTrue(ouverts[0].closed)
        self.assertFalse(conn.connecte)

    def test_ordre_inverse_a_la_fermeture(self):
        # À la déconnexion, le log doit ENCORE être ouvert ; il se ferme après
        ouverts, etats = [], []

        def sortie(message):
            if "Déconnexion" in message:
                etats.append(ouverts[0].closed)

        executer_tache(self.log, "X", sortie=sortie, ouvreur=espion(ouverts))
        self.assertEqual(etats, [False])
        self.assertTrue(ouverts[0].closed)


class TestSimulerErreur(BaseTest):
    def test_exception_propagee(self):
        with self.assertRaises(RuntimeError) as ctx:
            simuler_erreur(self.log, "Base Y", sortie=lambda m: None)
        self.assertEqual(str(ctx.exception), "Erreur de traitement")

    def test_les_deux_ressources_sont_fermees(self):
        ouverts, messages = [], []
        with self.assertRaises(RuntimeError):
            simuler_erreur(self.log, "Base Y", messages.append, espion(ouverts))
        self.assertTrue(ouverts[0].closed)
        self.assertTrue(any("Déconnexion de Base Y" in m for m in messages))
        self.assertTrue(any("RuntimeError — Erreur de traitement" in m for m in messages))

    def test_echec_de_connexion_ferme_quand_meme_le_log(self):
        # Le log est ouvert, puis la connexion échoue : le log doit être fermé
        ouverts = []
        from contextlib import ExitStack
        with self.assertRaises(ConnectionError):
            with ExitStack() as stack:
                stack.enter_context(espion(ouverts)(self.log, "a"))
                stack.enter_context(ConnectionManager("Z", echec_connexion=True))
        self.assertTrue(ouverts[0].closed)


class TestLogger(BaseTest):
    def test_horodatage_automatique(self):
        with Logger(self.log) as lg:
            lg.ecrire("démarrage")
            lg.ecrire("fin")
        lignes = Path(self.log).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 2)
        self.assertRegex(lignes[0], r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\] démarrage$")

    def test_ferme_apres_with_et_apres_erreur(self):
        lg = Logger(self.log)
        self.assertFalse(lg.ferme)  # pas encore ouvert
        with self.assertRaises(ValueError):
            with lg:
                raise ValueError()
        self.assertTrue(lg.ferme)


class TestConnecterPlusieurs(unittest.TestCase):
    def test_toutes_connectees_puis_deconnectees(self):
        with connecter_plusieurs(["A", "B", "C"], sortie=lambda m: None) as conns:
            self.assertEqual([c.service_name for c in conns], ["A", "B", "C"])
            self.assertTrue(all(c.connecte for c in conns))
        self.assertFalse(any(c.connecte for c in conns))

    def test_ordre_de_deconnexion_inverse(self):
        messages = []
        with connecter_plusieurs(["A", "B", "C"], sortie=messages.append):
            pass
        deconnexions = [m for m in messages if "Déconnexion" in m]
        self.assertIn("C", deconnexions[0])
        self.assertIn("B", deconnexions[1])
        self.assertIn("A", deconnexions[2])

    def test_si_la_2e_echoue_la_1ere_est_deconnectee(self):
        # La connexion "B" échoue : "A" doit être déconnectée
        from unittest import mock
        messages = []
        vrai = ConnectionManager

        def fabrique(service, sortie):
            return vrai(service, sortie, echec_connexion=(service == "B"))

        with mock.patch("connexion.ConnectionManager", fabrique):
            with self.assertRaises(ConnectionError):
                with connecter_plusieurs(["A", "B"], sortie=messages.append):
                    pass
        self.assertTrue(any("Déconnexion de A" in m for m in messages))

    def test_erreur_dans_le_bloc(self):
        with self.assertRaises(RuntimeError):
            with connecter_plusieurs(["A", "B"], sortie=lambda m: None) as conns:
                raise RuntimeError()
        self.assertFalse(any(c.connecte for c in conns))


if __name__ == "__main__":
    unittest.main()