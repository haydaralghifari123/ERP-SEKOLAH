# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from .common import NtiEduCommon


def _wali(env, siswa, partner, hubungan='ayah'):
    return env['nti_edu.siswa.wali'].create({
        'siswa_id': siswa.id, 'partner_id': partner.id, 'hubungan': hubungan})


@tagged('post_install', '-at_install')
class TestHelperPortal(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.anak_smp = cls._buat_siswa('Anak SMP', cls.unit_smp, '001')
        cls.anak_sma = cls._buat_siswa('Anak SMA', cls.unit_sma, '002')
        cls.wali = cls.env['res.partner'].create({'name': 'Wali Tes', 'email': 'wali.tes@example.com'})
        _wali(cls.env, cls.anak_smp, cls.wali)
        _wali(cls.env, cls.anak_sma, cls.wali, 'ibu')
        cls.user_wali = new_test_user(
            cls.env, login='tes_wali', groups='base.group_portal',
            company_id=cls.unit_smp.id, company_ids=[(6, 0, (cls.unit_smp | cls.unit_sma).ids)])
        cls.user_wali.write({'partner_id': cls.wali.id})
        cls.user_siswa = new_test_user(
            cls.env, login='tes_siswa', groups='base.group_portal',
            company_id=cls.unit_smp.id, company_ids=[(6, 0, cls.unit_smp.ids)])

    def test_wali_dua_unit(self):
        self.assertEqual(self.user_wali._nti_edu_siswa_portal(), self.anak_smp | self.anak_sma)

    def test_siswa_hanya_dirinya(self):
        user = new_test_user(
            self.env, login='tes_siswa2', groups='base.group_portal',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        siswa = user.partner_id
        siswa.write({'nti_edu_is_siswa': True, 'company_id': self.unit_smp.id, 'nti_edu_nis': '777'})
        self.assertEqual(user._nti_edu_siswa_portal(), siswa)

    def test_tanpa_anak_kosong(self):
        self.assertFalse(self.user_siswa._nti_edu_siswa_portal())
        self.assertFalse(self.user_operator_smp._nti_edu_siswa_portal())

    def test_pegawai_ortu(self):
        _wali(self.env, self.anak_sma, self.user_guru_smp.partner_id)
        self.assertEqual(self.user_guru_smp._nti_edu_siswa_portal(), self.anak_sma)

    def test_hanya_siswa_aktif(self):
        self.anak_sma.nti_edu_status = 'lulus'
        self.assertEqual(self.user_wali._nti_edu_siswa_portal(), self.anak_smp)
        self.anak_smp.active = False
        self.assertFalse(self.user_wali._nti_edu_siswa_portal())

    def test_hasil_sudo(self):
        self.assertTrue(self.user_wali._nti_edu_siswa_portal().env.su)


@tagged('post_install', '-at_install')
class TestRutePortal(HttpCase):

    def setUp(self):
        super().setUp()
        env = self.env
        env['nti_edu.tahun.ajaran'].search([('is_aktif', '=', True)]).write({'is_aktif': False})
        Company = env['res.company']
        yayasan = Company.create({'name': 'Yayasan Rute', 'nti_edu_jenis': 'yayasan'})
        self.unit_a = Company.create({
            'name': 'Unit Rute A', 'parent_id': yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': env.ref('nti_edu_base.jenjang_smp').id, 'nti_edu_kode': 'rta'})
        self.unit_b = Company.create({
            'name': 'Unit Rute B', 'parent_id': yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'rtb'})
        Partner = env['res.partner']

        def siswa(nama, unit, nis):
            return Partner.create({
                'name': nama, 'nti_edu_is_siswa': True, 'company_id': unit.id, 'nti_edu_nis': nis})

        self.anak1 = siswa('Budi Anak Satu', self.unit_a, '101')
        self.anak2 = siswa('Sari Anak Dua', self.unit_b, '102')
        self.orang_lain = siswa('Anak Orang Lain', self.unit_a, '103')
        self.siswa_diri = siswa('Siswa Mandiri', self.unit_a, '104')
        wali = Partner.create({'name': 'Ibu Wali', 'email': 'ibu.wali@example.com'})
        _wali(env, self.anak1, wali)
        _wali(env, self.anak2, wali, 'ibu')
        _wali(env, self.orang_lain, Partner.create({'name': 'Wali Lain', 'email': 'lain@example.com'}))
        self.user_wali = new_test_user(
            env, login='rute_wali', groups='base.group_portal', password='rute_wali',
            company_id=self.unit_a.id, company_ids=[(6, 0, (self.unit_a | self.unit_b).ids)])
        self.user_wali.write({'partner_id': wali.id})
        # Wali unit lain: tidak punya akses ke anak unit A.
        self.user_wali_b = new_test_user(
            env, login='rute_wali_b', groups='base.group_portal', password='rute_wali_b',
            company_id=self.unit_b.id, company_ids=[(6, 0, self.unit_b.ids)])
        wb = Partner.create({'name': 'Wali Unit B', 'email': 'wb@example.com'})
        _wali(env, self.anak2, wb)
        self.user_wali_b.write({'partner_id': wb.id})
        self.user_siswa = new_test_user(
            env, login='rute_siswa', groups='base.group_portal', password='rute_siswa',
            company_id=self.unit_a.id, company_ids=[(6, 0, self.unit_a.ids)])
        self.user_siswa.write({'partner_id': self.siswa_diri.id})
        self.user_nonsiswa = new_test_user(
            env, login='rute_biasa', groups='base.group_portal', password='rute_biasa',
            company_id=self.unit_a.id, company_ids=[(6, 0, self.unit_a.ids)])

    def test_daftar_anak_wali(self):
        self.authenticate('rute_wali', 'rute_wali')
        r = self.url_open('/my/anak')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Budi Anak Satu', r.text)
        self.assertIn('Sari Anak Dua', r.text)
        self.assertNotIn('Anak Orang Lain', r.text)

    def test_profil_anak_sendiri(self):
        self.authenticate('rute_wali', 'rute_wali')
        r = self.url_open('/my/anak/%d' % self.anak1.id)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Budi Anak Satu', r.text)
        self.assertIn('101', r.text)
        self.assertIn('Unit Rute A', r.text)

    def test_idor_anak_orang_lain(self):
        self.authenticate('rute_wali', 'rute_wali')
        for sid in (self.orang_lain.id, self.siswa_diri.id, self.user_wali.partner_id.id, 999999):
            self.assertEqual(self.url_open('/my/anak/%d' % sid).status_code, 404, sid)
            self.assertEqual(self.url_open('/my/anak/%d/pilih' % sid).status_code, 404, sid)
        # Wali unit B tidak bisa membuka anak unit A.
        self.authenticate('rute_wali_b', 'rute_wali_b')
        self.assertEqual(self.url_open('/my/anak/%d' % self.anak1.id).status_code, 404)
        self.assertEqual(self.url_open('/my/anak/%d' % self.anak2.id).status_code, 200)

    def test_user_tanpa_anak(self):
        self.authenticate('rute_biasa', 'rute_biasa')
        self.assertEqual(self.url_open('/my/anak').status_code, 200)
        self.assertEqual(self.url_open('/my/anak/%d' % self.anak1.id).status_code, 404)

    def test_siswa_profil_sendiri(self):
        self.authenticate('rute_siswa', 'rute_siswa')
        r = self.url_open('/my/anak/%d' % self.siswa_diri.id)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Siswa Mandiri', r.text)
        self.assertEqual(self.url_open('/my/anak/%d' % self.anak1.id).status_code, 404)
        self.assertIn('Profil Saya', self.url_open('/my/anak').text)

    def test_pilih_anak_aktif(self):
        self.authenticate('rute_wali', 'rute_wali')
        r = self.url_open('/my/anak')
        self.assertIn('data-anak-aktif="%d"' % self.anak1.id, r.text)  # bawaan: anak pertama
        r = self.url_open('/my/anak/%d/pilih' % self.anak2.id, allow_redirects=False)
        self.assertIn(r.status_code, (302, 303))
        self.assertTrue(r.headers['Location'].endswith('/my'))
        r = self.url_open('/my/anak')
        self.assertIn('data-anak-aktif="%d"' % self.anak2.id, r.text)
        self.assertNotIn('data-anak-aktif="%d"' % self.anak1.id, r.text)

    def test_anak_session_kedaluwarsa(self):
        """Anak di session yang tidak lagi diizinkan -> kembali ke anak pertama."""
        self.authenticate('rute_wali', 'rute_wali')
        self.url_open('/my/anak/%d/pilih' % self.anak2.id)
        self.anak2.nti_edu_status = 'lulus'
        r = self.url_open('/my/anak')
        self.assertIn('data-anak-aktif="%d"' % self.anak1.id, r.text)

    def test_beranda_ada_entri(self):
        self.authenticate('rute_wali', 'rute_wali')
        r = self.url_open('/my')
        self.assertIn('/my/anak', r.text)
        self.assertIn('Anak Saya', r.text)
        res = self.make_jsonrpc_request('/my/counters', {'counters': ['nti_edu_anak_count']})
        self.assertEqual(res['nti_edu_anak_count'], 2)

    # --- Siswa tidak boleh mengubah data partner sendiri lewat jalur swalayan ---

    def _post_akun(self, nama):
        return self.url_open('/my/account', data={
            'csrf_token': http.Request.csrf_token(self), 'name': nama, 'email': 'baru@example.com',
            'street': 'Jl Baru 1', 'city': 'Kota', 'country_id': str(self.env.ref('base.id').id),
            'zipcode': '12345', 'phone': '0811'})

    def test_siswa_tidak_bisa_ubah_akun(self):
        self.authenticate('rute_siswa', 'rute_siswa')
        self._post_akun('Nama Diganti')
        self.siswa_diri.invalidate_recordset()
        self.assertEqual(self.siswa_diri.name, 'Siswa Mandiri')
        self.assertNotEqual(self.siswa_diri.email, 'baru@example.com')

    def test_wali_boleh_ubah_akun(self):
        self.authenticate('rute_wali', 'rute_wali')
        self._post_akun('Ibu Wali Baru')
        self.user_wali.partner_id.invalidate_recordset()
        self.assertEqual(self.user_wali.partner_id.name, 'Ibu Wali Baru')

    def test_siswa_ubah_sandi_tetap_bisa(self):
        self.authenticate('rute_siswa', 'rute_siswa')
        r = self.url_open('/my/security', data={
            'csrf_token': http.Request.csrf_token(self), 'old': 'rute_siswa',
            'new1': 'sandi-baru-123', 'new2': 'sandi-baru-123'})
        self.assertEqual(r.status_code, 200)
        self.authenticate('rute_siswa', 'sandi-baru-123')
        self.assertEqual(self.url_open('/my').status_code, 200)


@tagged('post_install', '-at_install')
class TestUsersSiswaGuard(NtiEduCommon):

    def test_siswa_tidak_bisa_tulis_diri_sendiri(self):
        user = new_test_user(
            self.env, login='tes_siswa_g', groups='base.group_portal',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        user.partner_id.write({'nti_edu_is_siswa': True, 'company_id': self.unit_smp.id, 'nti_edu_nis': '555'})
        for vals in ({'name': 'X'}, {'email': 'x@example.com'}, {'image_1920': False}, {'phone': '1'},
                     {'street': 'x'}, {'name': 'X', 'tz': 'UTC'}):
            with self.assertRaises(AccessError, msg=str(vals)):
                user.with_user(user).write(vals)
        # Kata sandi dan preferensi non-partner tetap boleh.
        user.with_user(user).change_password('tes_siswa_g', 'sandi-baru-123')
        user.with_user(user).write({'signature': 'TTD'})

    def test_non_siswa_boleh(self):
        user = new_test_user(
            self.env, login='tes_wali_g', groups='base.group_portal',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        user.with_user(user).write({'name': 'Nama Baru'})
        self.assertEqual(user.partner_id.name, 'Nama Baru')
