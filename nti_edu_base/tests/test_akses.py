# -*- coding: utf-8 -*-
from datetime import date

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from odoo.tools import mute_logger

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

    # --- Hak tulis data master bersama ---
    def _libur(self, unit, tanggal=date(2026, 12, 1)):
        return self.env['nti_edu.hari.libur'].create({
            'name': 'Libur', 'tanggal_mulai': tanggal, 'company_id': unit.id if unit else False})

    def test_operator_tidak_ubah_libur_yayasan(self):
        libur = self._libur(self.yayasan)
        libur_op = libur.with_user(self.user_operator_smp)
        self.assertTrue(libur_op.read(['name']))
        with self.assertRaises(AccessError):
            libur_op.write({'name': 'Ubah'})
        with self.assertRaises(AccessError):
            libur_op.unlink()

    def test_operator_tidak_hapus_libur_global(self):
        libur = self._libur(False)
        with self.assertRaises(AccessError):
            libur.with_user(self.user_operator_smp).unlink()

    def test_operator_tidak_buat_libur_yayasan(self):
        with self.assertRaises(AccessError):
            self.env['nti_edu.hari.libur'].with_user(self.user_operator_smp).create({
                'name': 'X', 'tanggal_mulai': date(2026, 12, 2), 'company_id': self.yayasan.id})

    def test_operator_kelola_libur_unit_sendiri(self):
        libur = self.env['nti_edu.hari.libur'].with_user(self.user_operator_smp).create({
            'name': 'Libur SMP', 'tanggal_mulai': date(2026, 12, 3), 'company_id': self.unit_smp.id})
        libur.write({'name': 'Libur SMP 2'})
        # Hapus data hanya hak Admin Data Sekolah.
        with self.assertRaises(AccessError):
            libur.unlink()
        admin = self._buat_user('tes_admin_libur', 'nti_edu_base.group_base_admin', self.unit_smp)
        libur.with_user(admin).unlink()
        self.assertFalse(libur.exists())

    def test_admin_yayasan_buat_libur_tanpa_unit(self):
        admin = self._buat_user('tes_admin_yys', 'nti_edu_base.group_base_admin', self.yayasan)
        admin.company_ids = [(6, 0, (self.yayasan | self.unit_smp | self.unit_sma).ids)]
        Libur = self.env['nti_edu.hari.libur'].with_user(admin)
        libur = Libur.create({'name': 'Nasional', 'tanggal_mulai': date(2026, 12, 4)})
        libur.write({'name': 'Nasional 2'})
        libur_yys = Libur.create({
            'name': 'Yys', 'tanggal_mulai': date(2026, 12, 5), 'company_id': self.yayasan.id})
        libur_yys.unlink()

    def test_libur_jurusan_lintas_unit_terbaca(self):
        libur = self._libur(self.unit_sma)
        jurusan = self.env['nti_edu.jurusan'].create({'name': 'IPA', 'company_id': self.unit_sma.id})
        self.assertNotIn(libur, self.env['nti_edu.hari.libur'].with_user(self.user_guru_smp).search([]))
        self.assertNotIn(jurusan, self.env['nti_edu.jurusan'].with_user(self.user_guru_smp).search([]))
        self.assertIn(jurusan, self.env['nti_edu.jurusan'].with_user(self.user_guru_sma).search([]))

    # --- Model khusus unit ---
    def test_rombel_yayasan_ditolak(self):
        with self.assertRaises(ValidationError), mute_logger('odoo.sql_db'):
            self._rombel('Yys', self.env.ref('nti_edu_base.tingkat_smp_7'), self.yayasan)

    def test_ruang_yayasan_ditolak(self):
        with self.assertRaises(ValidationError):
            self.env['nti_edu.ruang'].create({'name': 'R Yys', 'company_id': self.yayasan.id})

    def test_ruang_dan_anggota_unit_lain_tak_terlihat(self):
        ruang = self.env['nti_edu.ruang'].create({'name': 'R SMA', 'company_id': self.unit_sma.id})
        anggota = self.env['nti_edu.rombel.anggota'].create(
            {'rombel_id': self.rombel_sma.id, 'siswa_id': self.siswa_sma.id})
        self.assertNotIn(ruang, self.env['nti_edu.ruang'].with_user(self.user_guru_smp).search([]))
        self.assertNotIn(
            anggota, self.env['nti_edu.rombel.anggota'].with_user(self.user_guru_smp).search([]))
        self.assertIn(ruang, self.env['nti_edu.ruang'].with_user(self.user_guru_sma).search([]))

    # --- Hak hapus: hanya admin (spec II.5); operator tidak boleh menghapus ---
    def _anggota_smp(self):
        return self.env['nti_edu.rombel.anggota'].create({
            'rombel_id': self.rombel_smp.id, 'siswa_id': self.siswa_smp.id})

    def test_operator_tidak_hapus_rombel_anggota_tahun(self):
        anggota = self._anggota_smp()
        operator = self.user_operator_smp
        with self.assertRaises(AccessError):
            self.rombel_smp.with_user(operator).unlink()
        with self.assertRaises(AccessError):
            anggota.with_user(operator).unlink()
        with self.assertRaises(AccessError):
            self.ta.with_user(operator).unlink()
        semester = self.env['nti_edu.semester'].create({
            'tahun_ajaran_id': self.ta.id, 'jenis': 'ganjil',
            'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2026, 12, 20)})
        with self.assertRaises(AccessError):
            semester.with_user(operator).unlink()
        libur = self._libur(self.unit_smp, date(2026, 12, 9))
        with self.assertRaises(AccessError):
            libur.with_user(operator).unlink()

    def test_operator_tetap_hapus_baris_wali(self):
        ibu = self.env['res.partner'].create({'name': 'Ibu SMP'})
        baris = self.env['nti_edu.siswa.wali'].create(
            {'siswa_id': self.siswa_smp.id, 'partner_id': ibu.id, 'hubungan': 'ibu'})
        baris.with_user(self.user_operator_smp).unlink()
        self.assertFalse(baris.exists())

    def test_operator_tidak_hapus_siswa_tapi_bisa_arsipkan(self):
        operator = self.user_operator_smp
        with self.assertRaises(AccessError):
            self.siswa_smp.with_user(operator).unlink()
        self.assertTrue(self.siswa_smp.exists())
        self.siswa_smp.with_user(operator).write({'active': False})
        self.assertFalse(self.siswa_smp.active)

    def test_admin_hapus_siswa_tanpa_riwayat(self):
        admin = self._buat_user('tes_admin_hapus3', 'nti_edu_base.group_base_admin', self.unit_smp)
        self.siswa_smp.with_user(admin).unlink()
        self.assertFalse(self.siswa_smp.exists())

    def test_admin_tidak_hapus_rombel_berisi_anggota(self):
        self._anggota_smp()
        admin = self._buat_user('tes_admin_hapus', 'nti_edu_base.group_base_admin', self.unit_smp)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.rombel_smp.with_user(admin).unlink()
        self.assertTrue(self.rombel_smp.exists())
        self.assertEqual(len(self.siswa_smp.nti_edu_anggota_ids), 1)

    def test_admin_hapus_rombel_kosong(self):
        admin = self._buat_user('tes_admin_hapus2', 'nti_edu_base.group_base_admin', self.unit_smp)
        kosong = self._rombel('VII Z', self.env.ref('nti_edu_base.tingkat_smp_7'), self.unit_smp)
        kosong.with_user(admin).unlink()
        self.assertFalse(kosong.exists())
