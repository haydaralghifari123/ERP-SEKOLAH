# -*- coding: utf-8 -*-
from datetime import date

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestRombel(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Tahun = cls.env['nti_edu.tahun.ajaran']
        cls.ta_lama = Tahun.create({
            'name': '2025/2026', 'tanggal_mulai': date(2025, 7, 14), 'tanggal_selesai': date(2026, 6, 30)})
        cls.ta_baru = Tahun.create({
            'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2027, 6, 30),
            'is_aktif': True})
        ref = cls.env.ref
        cls.rombel_7a = cls._rombel('VII A', cls.ta_lama, ref('nti_edu_base.tingkat_smp_7'), cls.unit_smp)
        cls.rombel_8a = cls._rombel('VIII A', cls.ta_baru, ref('nti_edu_base.tingkat_smp_8'), cls.unit_smp)
        cls.rombel_x = cls._rombel('X IPA 1', cls.ta_baru, ref('nti_edu_base.tingkat_sma_10'), cls.unit_sma)
        cls.siswa = cls._buat_siswa('Budi', cls.unit_smp, 'R001')

    @classmethod
    def _rombel(cls, nama, tahun, tingkat, unit):
        return cls.env['nti_edu.rombel'].create({
            'name': nama, 'tahun_ajaran_id': tahun.id, 'tingkat_id': tingkat.id, 'company_id': unit.id})

    def _jurusan(self, nama, company=None):
        return self.env['nti_edu.jurusan'].create({'name': nama, 'company_id': company.id if company else False})

    def test_jurusan_yayasan_dipakai_rombel_unit(self):
        jurusan = self._jurusan('IPA Yayasan', self.yayasan)
        self.rombel_x.jurusan_id = jurusan
        self.assertEqual(self.rombel_x.jurusan_id, jurusan)

    def test_jurusan_unit_lain_ditolak(self):
        jurusan = self._jurusan('IPA SMP', self.unit_smp)
        with self.assertRaises(UserError):
            self.rombel_x.jurusan_id = jurusan

    def test_domain_jurusan_rombel(self):
        global_ = self._jurusan('Global')
        yay = self._jurusan('Yayasan', self.yayasan)
        sma = self._jurusan('SMA', self.unit_sma)
        smp = self._jurusan('SMP', self.unit_smp)
        domain = self.env['nti_edu.jurusan']._check_company_domain(self.unit_sma)
        hasil = self.env['nti_edu.jurusan'].search(domain)
        self.assertEqual((global_ | yay | sma) - hasil, self.env['nti_edu.jurusan'])
        self.assertNotIn(smp, hasil)

    def _anggota(self, rombel, siswa=None, **vals):
        return self.env['nti_edu.rombel.anggota'].create(dict(
            vals, rombel_id=rombel.id, siswa_id=(siswa or self.siswa).id))

    def test_satu_rombel_per_tahun(self):
        lain = self._rombel('VIII B', self.ta_baru, self.env.ref('nti_edu_base.tingkat_smp_8'), self.unit_smp)
        pertama = self._anggota(self.rombel_8a)
        with self.assertRaises(ValidationError):
            self._anggota(lain)
        pertama.tanggal_keluar = date(2027, 1, 5)
        self._anggota(lain)

    def test_rombel_aktif_dan_riwayat(self):
        self._anggota(self.rombel_7a)
        self._anggota(self.rombel_8a)
        self.assertEqual(self.siswa.nti_edu_rombel_aktif_id, self.rombel_8a)
        self.assertEqual(self.siswa._nti_edu_rombel_pada(date(2025, 10, 1)), self.rombel_7a)
        self.assertFalse(self.siswa._nti_edu_rombel_pada(date(2024, 1, 1)))

    def test_jumlah_siswa(self):
        self._anggota(self.rombel_8a)
        keluar = self._anggota(self.rombel_8a, self._buat_siswa('Sari', self.unit_smp, 'R002'))
        self.assertEqual(self.rombel_8a.jumlah_siswa, 2)
        keluar.tanggal_keluar = date(2027, 1, 5)
        self.assertEqual(self.rombel_8a.jumlah_siswa, 1)

    def test_anggota_beda_unit_ditolak(self):
        with self.assertRaises(ValidationError):
            self._anggota(self.rombel_x)

    def test_hapus_tahun_ajaran_berrombel_ditolak(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.ta_baru.unlink()
        self.assertTrue(self.rombel_8a.exists())

    def test_nama_rombel_unik(self):
        tingkat = self.env.ref('nti_edu_base.tingkat_smp_8')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self._rombel('VIII A', self.ta_baru, tingkat, self.unit_smp)
        self._rombel('VIII A', self.ta_baru, self.env.ref('nti_edu_base.tingkat_sma_10'), self.unit_sma)

    def test_operator_kelola_keanggotaan_guru_tidak(self):
        anggota = self._anggota(self.rombel_8a)
        self.assertEqual(self.siswa.nti_edu_rombel_aktif_id, self.rombel_8a)
        # Operator mengubah keanggotaan: penghitungan ulang rombel aktif tidak boleh terhambat penjaga tulis.
        anggota.with_user(self.user_operator_smp).tanggal_keluar = date(2027, 1, 5)
        self.assertFalse(self.siswa.nti_edu_rombel_aktif_id)
        with self.assertRaises(AccessError):
            self.siswa.with_user(self.user_guru_smp).write({'nti_edu_anggota_ids': [(5,)]})

    def test_pindah_rombel_di_tengah_tahun(self):
        lain = self._rombel('VIII B', self.ta_baru, self.env.ref('nti_edu_base.tingkat_smp_8'), self.unit_smp)
        self._anggota(self.rombel_8a, tanggal_masuk=date(2026, 7, 13), tanggal_keluar=date(2026, 12, 1))
        self._anggota(lain, tanggal_masuk=date(2026, 12, 1))
        self.assertEqual(self.siswa._nti_edu_rombel_pada(date(2026, 11, 30)), self.rombel_8a)
        self.assertEqual(self.siswa._nti_edu_rombel_pada(date(2026, 12, 1)), lain)
        self.assertEqual(self.siswa._nti_edu_rombel_pada(date(2027, 2, 1)), lain)

    def test_tanggal_keluar_sebelum_masuk_ditolak(self):
        with self.assertRaises(ValidationError):
            self._anggota(self.rombel_8a, tanggal_masuk=date(2026, 8, 1), tanggal_keluar=date(2026, 7, 1))

    def test_ubah_unit_siswa_saat_masih_anggota_ditolak(self):
        self._anggota(self.rombel_8a)
        with self.assertRaises(ValidationError):
            self.siswa.company_id = self.unit_sma

    def test_ubah_unit_rombel_saat_berisi_anggota_ditolak(self):
        self._anggota(self.rombel_8a)
        with self.assertRaises(ValidationError):
            self.rombel_8a.company_id = self.unit_sma
