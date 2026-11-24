# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDemo(TransactionCase):
    """Memeriksa data demo; dilewati bila modul dipasang tanpa data demo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.yayasan = cls.env.ref('nti_edu_base.demo_yayasan', raise_if_not_found=False)

    def setUp(self):
        super().setUp()
        if not self.yayasan:
            self.skipTest('Data demo nti_edu_base tidak terpasang.')

    def _siswa_demo(self):
        imd = self.env['ir.model.data'].search([
            ('module', '=', 'nti_edu_base'), ('model', '=', 'res.partner'), ('name', '=like', 'demo_siswa_%')])
        return self.env['res.partner'].browse(imd.mapped('res_id'))

    def test_struktur_demo(self):
        smp = self.env.ref('nti_edu_base.demo_unit_smp')
        sma = self.env.ref('nti_edu_base.demo_unit_sma')
        self.assertEqual((smp.nti_edu_kode, sma.nti_edu_kode), ('smp1', 'sma1'))
        self.assertEqual(smp.parent_id, self.yayasan)
        self.assertEqual(sma.parent_id, self.yayasan)
        tahun = self.env['nti_edu.tahun.ajaran']._get_aktif()
        self.assertTrue(tahun)
        self.assertEqual(len(tahun.semester_ids), 2)
        rombel = self.env['nti_edu.rombel'].search([('tahun_ajaran_id', '=', tahun.id)])
        self.assertEqual(len(rombel.filtered(lambda r: r.company_id == smp)), 2)
        self.assertEqual(len(rombel.filtered(lambda r: r.company_id == sma)), 2)
        self.assertEqual(len(rombel.mapped('wali_kelas_id')), 1)
        self.assertEqual(self.env['nti_edu.hari.libur'].search_count([
            ('id', 'in', self.env['ir.model.data'].search([
                ('module', '=', 'nti_edu_base'), ('model', '=', 'nti_edu.hari.libur'),
                ('name', '=like', 'demo_%')]).mapped('res_id'))]), 3)

    def test_jumlah_siswa(self):
        siswa = self._siswa_demo()
        self.assertEqual(len(siswa), 20)
        self.assertTrue(all(s.nti_edu_rombel_aktif_id for s in siswa))

    def test_wali_bersaudara_portal(self):
        wali = self.env.ref('nti_edu_base.demo_wali_bersaudara')
        user = wali.user_ids
        self.assertEqual(len(user), 1)
        self.assertTrue(user.share)
        anak = user._nti_edu_siswa_portal()
        self.assertEqual(len(anak), 2)
        self.assertEqual(len(anak.mapped('company_id')), 2)
        self.assertEqual(user.company_ids, anak.mapped('company_id'))

    def test_user_demo(self):
        smp = self.env.ref('nti_edu_base.demo_unit_smp')
        sma = self.env.ref('nti_edu_base.demo_unit_sma')
        for xmlid in ('demo_user_operator', 'demo_user_guru1', 'demo_user_guru2', 'demo_user_guru3',
                      'demo_user_wali_bersaudara', 'demo_user_siswa'):
            self.assertTrue(self.env.ref('nti_edu_base.' + xmlid).login)
        operator = self.env.ref('nti_edu_base.demo_user_operator')
        self.assertTrue(operator.has_group('nti_edu_base.group_base_operator'))
        self.assertEqual(operator.company_ids, smp | sma)
        guru1 = self.env.ref('nti_edu_base.demo_user_guru1')
        self.assertEqual(self.env.ref('nti_edu_base.demo_rombel_7a').wali_kelas_id, guru1)
        siswa = self.env.ref('nti_edu_base.demo_user_siswa')
        self.assertEqual(len(siswa._nti_edu_siswa_portal()), 1)

    def test_admin_odoo_melihat_unit_demo(self):
        admin = self.env.ref('base.user_admin')
        for xmlid in ('demo_yayasan', 'demo_unit_smp', 'demo_unit_sma'):
            self.assertIn(self.env.ref('nti_edu_base.' + xmlid), admin.company_ids)
