# -*- coding: utf-8 -*-
"""Penjaga resource pegawai: company, status aktif, akun, nama, jam kerja, dan zona waktu pegawai disimpan di
resource.resource (field terkait hr.employee); menulis resource langsung tidak boleh melewati penjaga pegawai."""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import NtiPegawaiCommon

PESAN_UMUM = "lewat menu Pegawai"
PESAN_AKUN = "hanya boleh ditautkan oleh HRD"


@tagged('post_install', '-at_install')
class TestResourcePegawai(NtiPegawaiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hrd.write({'company_ids': [(4, cls.yayasan.id)]})
        cls.tu_yys = cls._buat_user(
            'peg_res_tu_yys', 'nti_edu_pegawai.group_pegawai_operator', cls.unit_smp | cls.yayasan)
        cls.staf = cls._buat_pegawai('Bu Bendahara Res', cls.yayasan, nti_edu_jenis_ptk='staf_yayasan')
        cls.tendik = cls._buat_pegawai('Pak Tendik Res', cls.unit_smp, nti_edu_jenis_ptk='tendik_admin')
        cls.kalender = cls.env['resource.calendar'].create({'name': 'Jam Kerja Res', 'company_id': cls.unit_smp.id})

    def _sebagai(self, rec, user):
        return rec.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def test_tu_ubah_staf_yayasan_lewat_resource_ditolak(self):
        resource = self._sebagai(self.staf.resource_id, self.tu_yys)
        for vals in ({'active': False}, {'name': 'Diganti TU'}, {'tz': 'Asia/Jakarta'},
                     {'calendar_id': self.kalender.id}):
            with self.assertRaisesRegex(AccessError, PESAN_UMUM):
                resource.write(vals)
        self.staf.invalidate_recordset()
        self.assertTrue(self.staf.active)
        self.assertEqual(self.staf.name, 'Bu Bendahara Res')
        self.assertNotEqual(self.staf.resource_id.tz, 'Asia/Jakarta')

    def test_tu_pindah_pegawai_unit_ke_yayasan_lewat_resource_ditolak(self):
        resource = self._sebagai(self.tendik.resource_id, self.tu_smp)
        with self.assertRaisesRegex(AccessError, PESAN_UMUM):
            resource.write({'company_id': self.yayasan.id})
        with self.assertRaisesRegex(AccessError, PESAN_UMUM):
            resource.write({'active': False})
        self.tendik.invalidate_recordset()
        self.assertEqual(self.tendik.company_id, self.unit_smp)
        self.assertTrue(self.tendik.active)

    def test_tu_tautkan_akun_lewat_resource_ditolak(self):
        with self.assertRaisesRegex(AccessError, PESAN_AKUN):
            self._sebagai(self.tendik.resource_id, self.tu_smp).write({'user_id': self.guru_smp.id})
        self.tendik.invalidate_recordset()
        self.assertFalse(self.tendik.user_id)
        # Membuat resource yang langsung memakai akun pun hanya HRD.
        with self.assertRaisesRegex(AccessError, PESAN_AKUN):
            self._sebagai(self.env['resource.resource'], self.tu_smp).create(
                {'name': 'Resource Akun', 'user_id': self.guru_smp.id, 'company_id': self.unit_smp.id})

    def test_tu_pakai_resource_pegawai_lain_ditolak(self):
        Emp = self._sebagai(self.env['hr.employee'], self.tu_smp)
        with self.assertRaisesRegex(AccessError, PESAN_UMUM):
            Emp.create({'name': 'Kembar', 'company_id': self.unit_smp.id, 'resource_id': self.tendik.resource_id.id})
        berakun = self.env['resource.resource'].create(
            {'name': 'Resource Berakun', 'user_id': self.guru_smp.id, 'company_id': self.unit_smp.id})
        with self.assertRaisesRegex(AccessError, PESAN_UMUM):
            Emp.create({'name': 'Berakun', 'company_id': self.unit_smp.id, 'resource_id': berakun.id})
        lain = self._buat_pegawai('Pak Lain Res', self.unit_smp)
        with self.assertRaisesRegex(AccessError, PESAN_UMUM):
            self._sebagai(lain, self.tu_smp).write({'resource_id': self.staf.resource_id.id})
        self.assertFalse(self.guru_smp.employee_ids)
        # Menyalin pegawai unit tanpa akun tetap bisa (resource baru hasil salinan).
        salinan = self._sebagai(self.tendik, self.tu_smp).copy()
        self.assertNotEqual(salinan.resource_id, self.tendik.resource_id)
        self.assertEqual(salinan.company_id, self.unit_smp)

    def test_tu_ubah_lewat_pegawai_tetap_bisa(self):
        tendik = self._sebagai(self.tendik, self.tu_smp)
        tendik.write({'name': 'Pak Tendik Baru', 'tz': 'Asia/Makassar', 'resource_calendar_id': self.kalender.id})
        self.assertEqual(self.tendik.resource_id.name, 'Pak Tendik Baru')
        self.assertEqual(self.tendik.resource_id.tz, 'Asia/Makassar')
        self.assertEqual(self.tendik.resource_id.calendar_id, self.kalender)
        tendik.action_archive()
        self.assertFalse(self.tendik.resource_id.active)
        tendik.action_unarchive()
        self.assertTrue(self.tendik.resource_id.active)
        # Pegawai baru oleh TU tetap membuat resource-nya.
        baru = self._sebagai(self.env['hr.employee'], self.tu_smp).create(
            {'name': 'Bu Baru Res', 'company_id': self.unit_smp.id})
        self.assertEqual(baru.resource_id.company_id, self.unit_smp)

    def test_tu_wizard_keberangkatan_pegawai_unit(self):
        Wizard = self._sebagai(self.env['hr.departure.wizard'], self.tu_smp).with_context(
            active_id=self.tendik.id, toggle_active=True)
        wizard = Wizard.create({
            'employee_id': self.tendik.id,
            'departure_reason_id': self.env['hr.departure.reason'].search([], limit=1).id,
        })
        wizard.action_register_departure()
        self.assertFalse(self.tendik.active)
        self.assertFalse(self.tendik.resource_id.active)

    def test_hrd_dan_resource_tanpa_pegawai_tidak_terpengaruh(self):
        self._sebagai(self.staf.resource_id, self.hrd).write({'name': 'Bu Bendahara HRD', 'tz': 'Asia/Jakarta'})
        self.assertEqual(self.staf.name, 'Bu Bendahara HRD')
        lepas = self.env['resource.resource'].create({'name': 'Ruang Rapat', 'company_id': self.unit_smp.id})
        self._sebagai(lepas, self.tu_smp).write({'name': 'Ruang Rapat Baru', 'tz': 'Asia/Jakarta'})
        self.assertEqual(lepas.name, 'Ruang Rapat Baru')
