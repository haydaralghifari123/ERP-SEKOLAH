# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestKontakAkun(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator_lain = cls._buat_user(
            'tes_operator_smp2', 'nti_edu_base.group_base_operator', cls.unit_smp)
        cls.admin = cls._buat_user(
            'tes_admin_erp', 'nti_edu_base.group_base_operator,base.group_erp_manager', cls.unit_smp)
        cls.user_arsip = cls._buat_user('tes_guru_arsip', 'nti_edu_base.group_base_pengguna', cls.unit_smp)
        cls.user_arsip.active = False
        for u in (cls.user_guru_smp, cls.operator_lain, cls.user_arsip):
            u.partner_id.write({'email': 'awal_%s@contoh.id' % u.login, 'phone': '111', 'mobile': '222'})

    def _partner(self, user):
        return user.partner_id.with_user(self.user_operator_smp)

    def test_operator_tak_bisa_ubah_email_akun_lain(self):
        for user in (self.user_guru_smp, self.user_arsip):
            for field, nilai in (('email', 'baru@contoh.id'), ('phone', '999'), ('mobile', '888')):
                lama = user.partner_id[field]
                with self.assertRaises(AccessError):
                    self._partner(user).write({field: nilai})
                self.assertEqual(user.partner_id.sudo()[field], lama)

    def test_operator_tak_bisa_ubah_email_akun_operator_lain(self):
        with self.assertRaises(AccessError):
            self._partner(self.operator_lain).write({'email': 'rebut@contoh.id'})

    def test_pemilik_boleh_ubah_kontaknya(self):
        user = self.user_guru_smp
        user.with_user(user).write({'email': 'sendiri@contoh.id'})
        self.assertEqual(user.partner_id.email, 'sendiri@contoh.id')

    def test_admin_boleh(self):
        self.operator_lain.partner_id.with_user(self.admin).write({'email': 'oleh_admin@contoh.id'})
        self.assertEqual(self.operator_lain.partner_id.email, 'oleh_admin@contoh.id')

    def test_kontak_tanpa_akun_tetap_bisa(self):
        biasa = self.env['res.partner'].create({'name': 'Kontak Biasa', 'company_id': self.unit_smp.id})
        biasa.with_user(self.user_operator_smp).write({'email': 'biasa@contoh.id'})
        siswa = self._buat_siswa('Siswa Kontak', self.unit_smp, '9001')
        siswa.with_user(self.user_operator_smp).write({'email': 'siswa@contoh.id'})
        self.assertEqual(biasa.email, 'biasa@contoh.id')
        self.assertEqual(siswa.email, 'siswa@contoh.id')

    def test_nilai_sama_tidak_ditolak(self):
        # Akun diarsipkan: pemeriksaan bawaan Odoo tidak berlaku, jadi hanya penjaga kita yang diuji.
        partner = self._partner(self.user_arsip)
        partner.write({'email': partner.sudo().email, 'phone': partner.sudo().phone})
