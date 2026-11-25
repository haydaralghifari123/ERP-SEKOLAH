# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import NtiPegawaiCommon


@tagged('post_install', '-at_install')
class TestModel(NtiPegawaiCommon):

    def test_instal_dan_grup(self):
        modul = self.env['ir.module.module'].search([('name', '=', 'nti_edu_pegawai')])
        self.assertEqual(modul.state, 'installed')
        operator = self.env.ref('nti_edu_pegawai.group_pegawai_operator')
        hrd = self.env.ref('nti_edu_pegawai.group_pegawai_hrd')
        self.assertIn(operator, hrd.implied_ids)
        self.assertIn(self.env.ref('nti_edu_base.group_base_pengguna'), operator.implied_ids)
        self.assertIn(self.env.ref('hr.group_hr_user'), operator.implied_ids)

    def _cek_unik(self, field):
        a = self._buat_pegawai('Budi Rahasia ' + field, self.unit_smp)
        a.work_contact_id.write({field: '12345'})
        b = self._buat_pegawai('Sari ' + field, self.unit_sma)
        with self.assertRaises(ValidationError) as ctx:
            b.work_contact_id.write({field: '12345'})
        pesan = str(ctx.exception)
        self.assertNotIn('Budi', pesan)
        self.assertNotIn(self.unit_smp.name, pesan)
        # Kontak arsip tetap dihitung.
        a.work_contact_id.active = False
        with self.assertRaises(ValidationError):
            b.work_contact_id.write({field: '12345'})

    def test_nuptk_unik_tanpa_bocor(self):
        self._cek_unik('nti_edu_nuptk')
        self._cek_unik('nti_edu_nip')
        # Kosong boleh berulang.
        c = self._buat_pegawai('C', self.unit_smp)
        d = self._buat_pegawai('D', self.unit_smp)
        c.work_contact_id.nti_edu_nuptk = False
        d.work_contact_id.nti_edu_nuptk = False

    def test_pegawai_wajib_unit(self):
        with self.assertRaises(ValidationError):
            self._buat_pegawai('Di Yayasan', self.yayasan)

    def test_unit_berpegawai_tak_bisa_jadi_yayasan(self):
        unit = self.env['res.company'].create({
            'name': 'SMK Tes Jenis', 'parent_id': self.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': self.env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'pgjns'})
        pegawai = self._buat_pegawai('Pak Jenis', unit)
        with self.assertRaises(ValidationError):
            unit.write({'nti_edu_jenis': 'yayasan'})
        # Hanya pegawai aktif yang menahan jenis unit.
        pegawai.write({'active': False})
        unit.write({'nti_edu_jenis': 'yayasan'})
        self.assertEqual(unit.nti_edu_jenis, 'yayasan')

    def test_guru_tidak_baca_profil(self):
        p = self._buat_pegawai('Pak Guru', self.unit_smp)
        p.work_contact_id.write({'nti_edu_nuptk': '999', 'nti_edu_nip': '888'})
        kontak = p.work_contact_id.with_user(self.guru_smp)
        with self.assertRaises(AccessError):
            kontak.nti_edu_nuptk
        with self.assertRaises(AccessError):
            kontak.nti_edu_nip

    def test_penanda_pegawai(self):
        p = self._buat_pegawai('Bu Guru', self.unit_smp)
        self.assertTrue(p.work_contact_id.nti_edu_is_pegawai)
        p.active = False
        self.assertFalse(p.work_contact_id.nti_edu_is_pegawai)
