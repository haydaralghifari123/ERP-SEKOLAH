# -*- coding: utf-8 -*-
from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestCompanyAdmin(NtiEduCommon):
    """Admin Data Sekolah hanya boleh mengubah field unit yang diizinkan pada res.company."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_smp = new_test_user(
            cls.env, login='tes_admin_company', groups='nti_edu_base.group_base_admin',
            company_id=cls.unit_smp.id, company_ids=[(6, 0, cls.unit_smp.ids)])

    def _unit(self):
        return self.unit_smp.with_user(self.admin_smp)

    def test_admin_ubah_field_unit(self):
        unit = self._unit()
        unit.write({'nti_edu_kode': 'smpx', 'name': 'SMP Tes Baru', 'phone': '021123', 'nti_edu_npsn': '123'})
        self.assertEqual(self.unit_smp.nti_edu_kode, 'smpx')
        self.assertEqual(self.unit_smp.name, 'SMP Tes Baru')

    def test_admin_tidak_ubah_user_ids(self):
        with self.assertRaises(AccessError):
            self._unit().write({'user_ids': [(4, self.user_guru_sma.id)]})
        self.assertNotIn(self.user_guru_sma, self.unit_smp.user_ids)

    def test_admin_tidak_arsipkan_atau_ubah_mata_uang(self):
        unit = self._unit()
        with self.assertRaises(AccessError):
            unit.write({'active': False})
        euro = self.env.ref('base.EUR')
        with self.assertRaises(AccessError):
            unit.write({'currency_id': euro.id})
        with self.assertRaises(AccessError):
            unit.write({'name': 'X', 'parent_id': False})
        self.assertTrue(self.unit_smp.active)

    def test_admin_tidak_ubah_unit_di_luar_akses(self):
        with self.assertRaises(AccessError):
            self.unit_sma.with_user(self.admin_smp).write({'name': 'Dibajak'})

    def test_kode_duplikat_terdeteksi_lintas_unit_tak_terlihat(self):
        # SMA tidak terlihat oleh admin SMP, namun kodenya tetap tidak boleh dipakai ulang.
        with self.assertRaises(ValidationError):
            self._unit().write({'nti_edu_kode': 'smat'})

    def test_kode_duplikat_dengan_unit_arsip(self):
        # Dibuat aktif lalu diarsipkan: membuat company langsung tidak aktif gagal di modul account
        # (company.parent_ids kosong untuk company arsip).
        arsip = self.env['res.company'].create({'name': 'Unit Arsip', 'nti_edu_kode': 'arsp'})
        arsip.active = False
        self.assertFalse(arsip.with_context(active_test=False).active)
        with self.assertRaises(ValidationError):
            self._unit().write({'nti_edu_kode': 'arsp'})

    def test_ubah_jenis_unit_berisi_rombel_ditolak(self):
        tahun = self.env['nti_edu.tahun.ajaran'].create({
            'name': '2026/2027', 'tanggal_mulai': date(2026, 7, 13), 'tanggal_selesai': date(2027, 6, 30)})
        self.env['nti_edu.rombel'].create({
            'name': 'VII A', 'tahun_ajaran_id': tahun.id,
            'tingkat_id': self.env.ref('nti_edu_base.tingkat_smp_7').id, 'company_id': self.unit_smp.id})
        with self.assertRaises(ValidationError):
            self.unit_smp.nti_edu_jenis = 'yayasan'

    def test_ubah_jenis_unit_berisi_siswa_ditolak(self):
        self.env['res.partner'].create({
            'name': 'Siswa Tes', 'nti_edu_is_siswa': True, 'company_id': self.unit_smp.id})
        with self.assertRaises(ValidationError):
            self.unit_smp.nti_edu_jenis = 'yayasan'

    def test_ubah_jenis_unit_berisi_ruang_ditolak(self):
        self.env['nti_edu.ruang'].create({'name': 'R1', 'company_id': self.unit_smp.id})
        with self.assertRaises(ValidationError):
            self.unit_smp.nti_edu_jenis = 'yayasan'
