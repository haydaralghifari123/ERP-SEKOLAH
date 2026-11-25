# -*- coding: utf-8 -*-
from datetime import date

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestKalender(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.unit_smp.nti_edu_hari_sekolah = '5'
        cls.unit_sma.nti_edu_hari_sekolah = '6'

    def _tahun(self, **kw):
        vals = {'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2027, 6, 30)}
        vals.update(kw)
        return self.env['nti_edu.tahun.ajaran'].create(vals)

    def test_tanggal_terbalik_ditolak(self):
        with self.assertRaises(ValidationError):
            self._tahun(tanggal_mulai=date(2027, 6, 30), tanggal_selesai=date(2026, 7, 13))

    def test_satu_tahun_aktif(self):
        aktif = self._tahun(is_aktif=True)
        self.assertEqual(self.env['nti_edu.tahun.ajaran']._get_aktif(), aktif)
        with self.assertRaises(ValidationError):
            self._tahun(name='2027/2028', tanggal_mulai=date(2027, 7, 12),
                        tanggal_selesai=date(2028, 6, 30), is_aktif=True)

    def test_get_aktif_kosong(self):
        self._tahun()
        self.assertFalse(self.env['nti_edu.tahun.ajaran']._get_aktif())

    def test_helper_spec_tahun_semester_aktif(self):
        tahun = self._tahun(is_aktif=True)
        smt = self.env['nti_edu.semester'].create({
            'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20), 'is_aktif': True})
        Company = self.env['res.company']
        self.assertEqual(Company._nti_edu_tahun_ajaran_aktif(), tahun)
        self.assertEqual(Company._nti_edu_semester_aktif(), smt)
        tahun.is_aktif = False
        self.assertFalse(Company._nti_edu_tahun_ajaran_aktif())
        self.assertFalse(Company._nti_edu_semester_aktif())

    def test_helper_aktif_untuk_portal(self):
        tahun = self._tahun(is_aktif=True)
        smt = self.env['nti_edu.semester'].create({
            'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20), 'is_aktif': True})
        portal = new_test_user(self.env, login='tes_portal_aktif', groups='base.group_portal')
        Company = self.env['res.company'].with_user(portal)
        self.assertEqual(Company._nti_edu_tahun_ajaran_aktif(), tahun)
        self.assertEqual(Company._nti_edu_semester_aktif(), smt)

    def test_hari_efektif_parameter_company(self):
        self.unit_smp.nti_edu_hari_sekolah = '6'
        self.unit_sma.nti_edu_hari_sekolah = '5'
        sabtu = date(2026, 8, 1)
        Company = self.env['res.company']
        self.assertIs(Company._nti_edu_hari_efektif(sabtu, company=self.unit_smp), True)
        self.assertIs(Company._nti_edu_hari_efektif(sabtu, company=self.unit_sma), False)
        # Parameter company menang atas self.
        self.assertIs(self.unit_sma._nti_edu_hari_efektif(sabtu, company=self.unit_smp), True)

    def test_hari_efektif_tanpa_company_memakai_company_aktif(self):
        self.unit_sma.nti_edu_hari_sekolah = '5'
        Company = self.env['res.company'].with_company(self.unit_sma)
        self.assertIs(Company._nti_edu_hari_efektif(date(2026, 8, 1)), False)
        self.assertIs(Company._nti_edu_hari_efektif(date(2026, 8, 3)), True)

    def test_semester_di_luar_tahun_ditolak(self):
        tahun = self._tahun()
        with self.assertRaises(ValidationError):
            self.env['nti_edu.semester'].create({
                'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
                'tanggal_mulai': date(2026, 6, 1), 'tanggal_selesai': date(2026, 12, 20)})

    def test_semester_nama_dan_aktif(self):
        tahun = self._tahun(is_aktif=True)
        smt = self.env['nti_edu.semester'].create({
            'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20), 'is_aktif': True})
        self.assertEqual(smt.name, '2026/2027 - Ganjil')
        self.assertEqual(self.env['nti_edu.semester']._get_aktif(), smt)

    def test_satu_semester_aktif_per_tahun(self):
        tahun = self._tahun()
        Semester = self.env['nti_edu.semester']
        Semester.create({
            'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20), 'is_aktif': True})
        with self.assertRaises(ValidationError):
            Semester.create({
                'tahun_ajaran_id': tahun.id, 'jenis': 'genap',
                'tanggal_mulai': date(2027, 1, 4), 'tanggal_selesai': date(2027, 6, 30), 'is_aktif': True})

    def test_semester_jenis_unik(self):
        tahun = self._tahun()
        vals = {'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
                'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20)}
        self.env['nti_edu.semester'].create(vals)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['nti_edu.semester'].create(vals)

    def test_tahun_dengan_semester_tidak_bisa_dihapus(self):
        tahun = self._tahun()
        self.env['nti_edu.semester'].create({
            'tahun_ajaran_id': tahun.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20)})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            tahun.unlink()

    def test_hari_efektif_akhir_pekan(self):
        sabtu, minggu, senin = date(2026, 7, 18), date(2026, 7, 19), date(2026, 7, 20)
        self.assertFalse(self.unit_smp._nti_edu_hari_efektif(sabtu))
        self.assertTrue(self.unit_sma._nti_edu_hari_efektif(sabtu))
        self.assertFalse(self.unit_smp._nti_edu_hari_efektif(minggu))
        self.assertFalse(self.unit_sma._nti_edu_hari_efektif(minggu))
        self.assertTrue(self.unit_smp._nti_edu_hari_efektif(senin))

    def test_libur_unit_dan_yayasan(self):
        Libur = self.env['nti_edu.hari.libur']
        Libur.create({'name': 'HUT RI', 'tanggal_mulai': date(2026, 8, 17), 'jenis': 'nasional'})
        Libur.create({'name': 'Libur SMP', 'tanggal_mulai': date(2026, 8, 18),
                      'company_id': self.unit_smp.id, 'jenis': 'sekolah'})
        Libur.create({'name': 'Libur Yayasan', 'tanggal_mulai': date(2026, 8, 19),
                      'company_id': self.yayasan.id, 'jenis': 'sekolah'})
        for unit in (self.unit_smp, self.unit_sma):
            self.assertFalse(unit._nti_edu_hari_efektif(date(2026, 8, 17)))
            self.assertFalse(unit._nti_edu_hari_efektif(date(2026, 8, 19)))
        self.assertFalse(self.unit_smp._nti_edu_hari_efektif(date(2026, 8, 18)))
        self.assertTrue(self.unit_sma._nti_edu_hari_efektif(date(2026, 8, 18)))

    def test_libur_ikut_terhapus_bersama_unit(self):
        unit = self.env['res.company'].create({'name': 'Unit Sementara', 'parent_id': self.yayasan.id})
        libur = self.env['nti_edu.hari.libur'].create({
            'name': 'Libur Unit', 'tanggal_mulai': date(2026, 8, 18), 'company_id': unit.id})
        unit.unlink()
        self.assertFalse(libur.exists())

    def test_libur_rentang(self):
        self.env['nti_edu.hari.libur'].create({
            'name': 'Ujian', 'tanggal_mulai': date(2026, 12, 7),
            'tanggal_selesai': date(2026, 12, 9), 'jenis': 'ujian'})
        self.assertFalse(self.unit_smp._nti_edu_hari_efektif(date(2026, 12, 8)))
        self.assertTrue(self.unit_smp._nti_edu_hari_efektif(date(2026, 12, 10)))

    def test_libur_satu_hari(self):
        self.env['nti_edu.hari.libur'].create({
            'name': 'Libur', 'tanggal_mulai': date(2026, 8, 20), 'jenis': 'lainnya'})
        self.assertFalse(self.unit_smp._nti_edu_hari_efektif(date(2026, 8, 20)))
        self.assertTrue(self.unit_smp._nti_edu_hari_efektif(date(2026, 8, 21)))

    def test_libur_tanggal_terbalik_ditolak(self):
        with self.assertRaises(ValidationError):
            self.env['nti_edu.hari.libur'].create({
                'name': 'X', 'tanggal_mulai': date(2026, 8, 20), 'tanggal_selesai': date(2026, 8, 19)})

    def test_ubah_tahun_ajaran_mengecilkan_rentang_ditolak(self):
        tahun = self._tahun()
        self.env['nti_edu.semester'].create({
            'tahun_ajaran_id': tahun.id, 'jenis': 'genap',
            'tanggal_mulai': date(2027, 1, 4), 'tanggal_selesai': date(2027, 6, 30)})
        with self.assertRaises(ValidationError):
            tahun.tanggal_selesai = date(2027, 5, 31)
