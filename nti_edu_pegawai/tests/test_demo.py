# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDemo(TransactionCase):
    """Memeriksa data demo pegawai; dilewati bila modul dipasang tanpa data demo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.guru2_smp = cls.env.ref('nti_edu_pegawai.demo_pegawai_guru2_smp', raise_if_not_found=False)

    def setUp(self):
        super().setUp()
        if not self.guru2_smp:
            self.skipTest('Data demo nti_edu_pegawai tidak terpasang.')

    def test_guru_dua_unit(self):
        guru2_sma = self.env.ref('nti_edu_pegawai.demo_pegawai_guru2_sma')
        user = self.env.ref('nti_edu_base.demo_user_guru2')
        smp = self.env.ref('nti_edu_base.demo_unit_smp')
        sma = self.env.ref('nti_edu_base.demo_unit_sma')
        self.assertEqual(self.guru2_smp.company_id, smp)
        self.assertEqual(guru2_sma.company_id, sma)
        self.assertTrue(self.guru2_smp.work_contact_id)
        self.assertEqual(self.guru2_smp.work_contact_id, guru2_sma.work_contact_id)
        self.assertEqual(self.guru2_smp.work_contact_id, user.partner_id)
        self.assertEqual(user.company_ids & (smp | sma), smp | sma)
        # Profil per orang terlihat dari kedua penempatan.
        self.assertEqual(guru2_sma.nti_edu_nuptk, '1234567890120002')
        self.assertEqual(len(self.guru2_smp.nti_edu_sertifikasi_ids), 2)

    def test_hrd_demo(self):
        hrd = self.env['res.users'].search([('login', '=', 'hrd.demo')])
        self.assertEqual(len(hrd), 1)
        self.assertTrue(hrd.has_group('nti_edu_pegawai.group_pegawai_hrd'))
        self.assertEqual(hrd.company_ids & self.env['res.company'].search([('nti_edu_jenis', '=', 'unit')]),
                         self.env.ref('nti_edu_base.demo_unit_smp') | self.env.ref('nti_edu_base.demo_unit_sma'))
        yayasan = self.env.ref('nti_edu_base.demo_yayasan')
        self.assertIn(yayasan, hrd.company_ids)
        # HRD Demo juga staf yayasan.
        staf = self.env.ref('nti_edu_pegawai.demo_pegawai_hrd')
        self.assertEqual(staf.company_id, yayasan)
        self.assertEqual(staf.user_id, hrd)
        self.assertEqual(staf.nti_edu_jenis_ptk, 'staf_yayasan')

    def test_bendahara_yayasan_tanpa_akun(self):
        bendahara = self.env.ref('nti_edu_pegawai.demo_pegawai_bendahara')
        self.assertEqual(bendahara.company_id, self.env.ref('nti_edu_base.demo_yayasan'))
        self.assertEqual(bendahara.nti_edu_jenis_ptk, 'staf_yayasan')
        self.assertFalse(bendahara.user_id)
        self.assertTrue(bendahara.work_contact_id.email)

    def test_operator_pegawai(self):
        operator = self.env.ref('nti_edu_base.demo_user_operator')
        self.assertTrue(operator.has_group('nti_edu_pegawai.group_pegawai_operator'))
        self.assertEqual(self.env.ref('nti_edu_pegawai.demo_pegawai_operator').user_id, operator)

    def test_kepala_sekolah_dan_tendik(self):
        kepsek = self.env.ref('nti_edu_pegawai.demo_pegawai_guru3')
        self.assertEqual(kepsek.nti_edu_jenis_ptk, 'kepala_sekolah')
        self.assertEqual(kepsek.user_id, self.env.ref('nti_edu_base.demo_user_guru3'))
        tendik = self.env.ref('nti_edu_pegawai.demo_pegawai_tendik')
        self.assertEqual(tendik.nti_edu_jenis_ptk, 'tendik_admin')
        self.assertFalse(tendik.user_id)
        self.assertTrue(tendik.work_contact_id.email)

    def test_semua_pegawai_di_unit_atau_yayasan(self):
        imd = self.env['ir.model.data'].search([
            ('module', '=', 'nti_edu_pegawai'), ('model', '=', 'hr.employee'), ('name', '=like', 'demo_pegawai_%')])
        pegawai = self.env['hr.employee'].browse(imd.mapped('res_id'))
        self.assertEqual(len(pegawai), 8)
        di_yayasan = pegawai.filtered(lambda p: p.company_id.nti_edu_jenis == 'yayasan')
        self.assertEqual(len(di_yayasan), 2)
        self.assertTrue(all(p.nti_edu_jenis_ptk == 'staf_yayasan' for p in di_yayasan))
        self.assertTrue(all(p.company_id.nti_edu_jenis == 'unit' for p in pegawai - di_yayasan))
        sertifikasi = self.env['nti_edu.pegawai.sertifikasi'].search([('nomor', '=like', 'SERT-DEMO-%')])
        self.assertEqual(len(sertifikasi), 4)
