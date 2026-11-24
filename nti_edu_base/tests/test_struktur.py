# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestStruktur(NtiEduCommon):

    def test_rantai_grup(self):
        self.assertTrue(self.user_operator_smp.has_group('nti_edu_base.group_base_pengguna'))
        self.assertTrue(self.user_operator_smp.has_group('base.group_partner_manager'))
        self.assertFalse(self.user_guru_smp.has_group('nti_edu_base.group_base_operator'))

    def test_admin_odoo_di_grup_admin(self):
        self.assertTrue(self.env.ref('base.user_admin').has_group('nti_edu_base.group_base_admin'))

    def test_data_jenjang(self):
        sma = self.env.ref('nti_edu_base.jenjang_sma')
        self.assertEqual(sma.tingkat_ids.mapped('urutan'), [10, 11, 12])
        self.assertTrue(self.env.ref('nti_edu_base.tingkat_sma_12').is_akhir)
        self.assertFalse(self.env.ref('nti_edu_base.tingkat_sma_11').is_akhir)

    def test_unit_adalah_branch(self):
        self.assertEqual(self.unit_smp.parent_id, self.yayasan)
        self.assertEqual(self.unit_smp.root_id, self.yayasan)

    def test_kode_unit_unik(self):
        with self.assertRaises(ValidationError):
            self.env['res.company'].create({'name': 'SMP Lain', 'nti_edu_kode': 'smpt'})

    def test_kode_kosong_boleh_berulang(self):
        self.env['res.company'].create([{'name': 'K1'}, {'name': 'K2'}])
