# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInstal(TransactionCase):

    def test_modul_terpasang(self):
        modul = self.env['ir.module.module'].search([('name', '=', 'nti_edu_base')])
        self.assertEqual(modul.state, 'installed')
