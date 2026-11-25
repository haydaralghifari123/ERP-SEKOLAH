# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.fields import Date
from odoo.tests import Form, tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestKenaikan(NtiEduCommon):

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
        cls.rombel_9a = cls._rombel('IX A', cls.ta_lama, ref('nti_edu_base.tingkat_smp_9'), cls.unit_smp)
        cls.rombel_x = cls._rombel('X IPA 1', cls.ta_baru, ref('nti_edu_base.tingkat_sma_10'), cls.unit_sma)
        cls.siswa_ids = [cls._buat_siswa('Siswa %d' % i, cls.unit_smp, 'K%03d' % i) for i in range(3)]

    @classmethod
    def _rombel(cls, nama, tahun, tingkat, unit):
        return cls.env['nti_edu.rombel'].create({
            'name': nama, 'tahun_ajaran_id': tahun.id, 'tingkat_id': tingkat.id, 'company_id': unit.id})

    def _isi(self, rombel):
        for siswa in self.siswa_ids:
            self.env['nti_edu.rombel.anggota'].create({'rombel_id': rombel.id, 'siswa_id': siswa.id})

    def _wizard(self, rombel_asal, rombel_tujuan=None, user=None):
        Wizard = self.env['nti_edu.kenaikan.kelas.wizard']
        if user:
            Wizard = Wizard.with_user(user)
        return Wizard.create({
            'rombel_asal_id': rombel_asal.id, 'rombel_tujuan_id': rombel_tujuan.id if rombel_tujuan else False})

    def test_naik_kelas(self):
        self._isi(self.rombel_7a)
        wizard = self._wizard(self.rombel_7a, self.rombel_8a)
        self.assertEqual(len(wizard.baris_ids), 3)
        self.assertEqual(set(wizard.baris_ids.mapped('aksi')), {'naik'})
        self.assertEqual(wizard.baris_ids.mapped('rombel_tujuan_id'), self.rombel_8a)
        wizard.action_proses()
        for siswa in self.siswa_ids:
            self.assertEqual(len(siswa.nti_edu_anggota_ids), 2)
            self.assertEqual(siswa.nti_edu_rombel_aktif_id, self.rombel_8a)
            self.assertIn(self.rombel_7a, siswa.nti_edu_anggota_ids.rombel_id)
            self.assertEqual(siswa.nti_edu_status, 'aktif')

    def test_tingkat_akhir_lulus(self):
        self._isi(self.rombel_9a)
        wizard = self._wizard(self.rombel_9a)
        self.assertEqual(set(wizard.baris_ids.mapped('aksi')), {'lulus'})
        wizard.action_proses()
        for siswa in self.siswa_ids:
            self.assertEqual(siswa.nti_edu_status, 'lulus')
            # Hari keluar bersifat eksklusif: siswa tetap anggota pada hari terakhir tahun ajaran.
            self.assertEqual(siswa.nti_edu_anggota_ids.tanggal_keluar, date(2026, 7, 1))
            self.assertEqual(siswa._nti_edu_rombel_pada(date(2026, 6, 30)), self.rombel_9a)

    def test_tahun_tujuan_sama_ditolak(self):
        self._isi(self.rombel_7a)
        lain = self._rombel('VII B', self.ta_lama, self.env.ref('nti_edu_base.tingkat_smp_7'), self.unit_smp)
        with self.assertRaises(UserError):
            self._wizard(self.rombel_7a, lain).action_proses()

    def test_tujuan_wajib_untuk_naik(self):
        self._isi(self.rombel_7a)
        with self.assertRaises(UserError):
            self._wizard(self.rombel_7a).action_proses()

    def test_tujuan_beda_unit_ditolak(self):
        self._isi(self.rombel_7a)
        with self.assertRaises(UserError):
            self._wizard(self.rombel_7a, self.rombel_x).action_proses()

    def test_tinggal_kelas(self):
        self._isi(self.rombel_7a)
        tujuan = self._rombel('VII A', self.ta_baru, self.env.ref('nti_edu_base.tingkat_smp_7'), self.unit_smp)
        wizard = self._wizard(self.rombel_7a, tujuan)
        wizard.baris_ids.write({'aksi': 'tinggal'})
        wizard.action_proses()
        for siswa in self.siswa_ids:
            self.assertEqual(siswa.nti_edu_rombel_aktif_id, tujuan)

    def test_proses_dua_kali_ditolak(self):
        self._isi(self.rombel_7a)
        wizard = self._wizard(self.rombel_7a, self.rombel_8a)
        wizard.action_proses()
        with self.assertRaises(UserError):
            wizard.action_proses()
        for siswa in self.siswa_ids:
            self.assertEqual(len(siswa.nti_edu_anggota_ids), 2)

    def test_rombel_asal_kosong(self):
        wizard = self._wizard(self.rombel_7a, self.rombel_8a)
        self.assertFalse(wizard.baris_ids)
        wizard.action_proses()

    def test_operator_unit_menjalankan_wizard_guru_tidak(self):
        self._isi(self.rombel_7a)
        wizard = self._wizard(self.rombel_7a, self.rombel_8a, user=self.user_operator_smp)
        self.assertEqual(len(wizard.baris_ids), 3)
        wizard.action_proses()
        for siswa in self.siswa_ids:
            self.assertEqual(siswa.nti_edu_rombel_aktif_id, self.rombel_8a)
        with self.assertRaises(AccessError):
            self._wizard(self.rombel_7a, self.rombel_8a, user=self.user_guru_smp)

    def test_operator_lulus(self):
        self._isi(self.rombel_9a)
        self._wizard(self.rombel_9a, user=self.user_operator_smp).action_proses()
        self.assertEqual({s.nti_edu_status for s in self.siswa_ids}, {'lulus'})

    def test_status_pindah_tutup_anggota(self):
        self._isi(self.rombel_8a)
        siswa = self.siswa_ids[0]
        self.assertEqual(siswa.nti_edu_rombel_aktif_id, self.rombel_8a)
        siswa.nti_edu_status = 'pindah'
        self.assertEqual(siswa.nti_edu_anggota_ids.tanggal_keluar, Date.context_today(siswa))
        self.assertFalse(siswa.nti_edu_rombel_aktif_id)

    def test_status_keluar_oleh_operator(self):
        self._isi(self.rombel_8a)
        siswa = self.siswa_ids[1]
        siswa.with_user(self.user_operator_smp).nti_edu_status = 'keluar'
        self.assertEqual(siswa.nti_edu_anggota_ids.tanggal_keluar, Date.context_today(siswa))
        self.assertFalse(siswa.nti_edu_rombel_aktif_id)

    def test_form_wizard_lewat_tampilan(self):
        """Regresi: baris siswa harus tersimpan saat wizard diisi lewat form (siswa_id readonly + force_save)."""
        self._isi(self.rombel_7a)
        wizard_op = self.env['nti_edu.kenaikan.kelas.wizard'].with_user(self.user_operator_smp).with_context(
            default_rombel_asal_id=self.rombel_7a.id)
        form = Form(wizard_op, view='nti_edu_base.view_kenaikan_kelas_wizard_form')
        form.rombel_tujuan_id = self.rombel_8a
        wizard = form.save()
        self.assertEqual(len(wizard.baris_ids), 3)
        self.assertEqual(set(wizard.baris_ids.siswa_id.ids), {s.id for s in self.siswa_ids})
        wizard.action_proses()
        for siswa in self.siswa_ids:
            self.assertEqual(siswa.nti_edu_rombel_aktif_id, self.rombel_8a)
            self.assertEqual(len(siswa.nti_edu_anggota_ids), 2)
