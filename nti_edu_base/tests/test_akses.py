# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestAkses(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.ta = cls.env['nti_edu.tahun.ajaran'].create({
            'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2027, 6, 30)})
        cls.siswa_smp = cls._buat_siswa('Siswa SMP', cls.unit_smp, 'A001')
        cls.siswa_sma = cls._buat_siswa('Siswa SMA', cls.unit_sma, 'A002')
        cls.wali = cls.env['res.partner'].create({'name': 'Wali SMP', 'company_id': cls.unit_smp.id})
        cls.env['nti_edu.siswa.wali'].create(
            {'siswa_id': cls.siswa_smp.id, 'partner_id': cls.wali.id, 'hubungan': 'ayah'})
        cls.rombel_smp = cls._rombel('VII A', ref('nti_edu_base.tingkat_smp_7'), cls.unit_smp)
        cls.rombel_sma = cls._rombel('X A', ref('nti_edu_base.tingkat_sma_10'), cls.unit_sma)
        cls.biasa = cls.env['res.partner'].create({'name': 'Mitra Biasa'})

    @classmethod
    def _rombel(cls, nama, tingkat, unit):
        return cls.env['nti_edu.rombel'].create({
            'name': nama, 'tahun_ajaran_id': cls.ta.id, 'tingkat_id': tingkat.id, 'company_id': unit.id})

    def test_guru_unit_lain_tidak_lihat(self):
        siswa = self.env['res.partner'].with_user(self.user_guru_sma).search([('nti_edu_is_siswa', '=', True)])
        self.assertNotIn(self.siswa_smp, siswa)
        self.assertIn(self.siswa_sma, siswa)
        rombel = self.env['nti_edu.rombel'].with_user(self.user_guru_sma).search([])
        self.assertNotIn(self.rombel_smp, rombel)
        self.assertIn(self.rombel_sma, rombel)

    def test_guru_unit_sama_lihat(self):
        siswa = self.env['res.partner'].with_user(self.user_guru_smp).search([('nti_edu_is_siswa', '=', True)])
        self.assertIn(self.siswa_smp, siswa)
        rombel = self.env['nti_edu.rombel'].with_user(self.user_guru_smp).search([])
        self.assertIn(self.rombel_smp, rombel)

    def test_master_unit_lain_tidak_lihat(self):
        Mapel = self.env['nti_edu.mapel']
        mapel_smp = Mapel.create({'name': 'IPA SMP', 'company_id': self.unit_smp.id})
        self.assertNotIn(mapel_smp, Mapel.with_user(self.user_guru_sma).search([]))
        self.assertIn(mapel_smp, Mapel.with_user(self.user_guru_smp).search([]))

    def test_master_yayasan_terlihat_unit(self):
        Mapel = self.env['nti_edu.mapel']
        mapel = Mapel.create({'name': 'Agama Yayasan', 'company_id': self.yayasan.id})
        global_ = Mapel.create({'name': 'Tanpa Unit'})
        hasil = Mapel.with_user(self.user_guru_smp).search([])
        self.assertIn(mapel, hasil)
        self.assertIn(global_, hasil)

    def test_hari_efektif_libur_yayasan_untuk_non_superuser(self):
        self.env['nti_edu.hari.libur'].create({
            'name': 'Libur Yayasan', 'tanggal_mulai': date(2026, 11, 25), 'company_id': self.yayasan.id})
        unit = self.unit_smp.with_user(self.user_guru_smp)
        self.assertFalse(unit._nti_edu_hari_efektif(date(2026, 11, 25)))
        self.assertTrue(unit._nti_edu_hari_efektif(date(2026, 11, 26)))

    def test_eksternal_tidak_lihat_siswa_wali(self):
        Partner = self.env['res.partner'].with_user(self.user_eksternal)
        Partner.invalidate_model()
        self.assertFalse(Partner.search([('id', 'in', [self.siswa_smp.id, self.wali.id])]))
        self.assertFalse(Partner.name_search(self.siswa_smp.name))
        self.assertFalse(Partner.name_search(self.wali.name))
        self.assertIn(self.biasa, Partner.search([('id', '=', self.biasa.id)]))

    def test_eksternal_tanpa_akses_rombel(self):
        with self.assertRaises(AccessError):
            self.env['nti_edu.rombel'].with_user(self.user_eksternal).search([])
