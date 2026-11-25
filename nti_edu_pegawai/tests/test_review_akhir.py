# -*- coding: utf-8 -*-
"""Tes hasil tinjauan akhir: tautan kontak kerja, profil saat buat, sinkron email kerja, akses akun."""
from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import NtiPegawaiCommon
from ..models.hr_employee import PROFIL_TERKAIT


class _DasarReview(NtiPegawaiCommon):

    def _sebagai(self, rec, user):
        return rec.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def _akun(self, pegawai, login, units, grup='nti_edu_base.group_base_pengguna'):
        """Akun login untuk kontak kerja `pegawai`, ditautkan ke record itu (sebagai superuser)."""
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': pegawai.name, 'login': login, 'partner_id': pegawai.work_contact_id.id,
            'company_id': units[0].id, 'company_ids': [(6, 0, units.ids)],
            'groups_id': [(6, 0, [self.env.ref(grup).id])],
        })
        pegawai.write({'user_id': user.id})
        return user

    def _dua_unit_berakun(self, login='orang_dua'):
        """Satu orang di SMP dan SMA dengan satu akun yang memegang kedua unit."""
        smp = self._buat_pegawai('Orang Dua', self.unit_smp, work_email=login + '@contoh.id')
        user = self._akun(smp, login, self.unit_smp | self.unit_sma)
        sma = self._buat_pegawai(
            'Orang Dua', self.unit_sma, work_contact_id=smp.work_contact_id.id, user_id=user.id)
        return smp, sma, user


@tagged('post_install', '-at_install')
class TestTautanKontak(_DasarReview):
    """Kritis 1: menautkan kontak kerja tidak boleh membuka data/akun orang lain."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.wali = Partner.create({
            'name': 'Wali Tes', 'email': 'wali@contoh.id', 'nti_edu_nik': '3201000000000101'})
        cls.siswa_sma = Partner.create({
            'name': 'Siswa Tes', 'nti_edu_is_siswa': True, 'company_id': cls.unit_sma.id,
            'email': 'siswa@contoh.id', 'nti_edu_nik': '3201000000000102'})
        cls.env['nti_edu.siswa.wali'].create({'siswa_id': cls.siswa_sma.id, 'partner_id': cls.wali.id})
        cls.lain = new_test_user(
            cls.env, login='peg_user_lain', groups='base.group_user', company_id=cls.unit_sma.id,
            company_ids=[(6, 0, cls.unit_sma.ids)], email='lain@contoh.id')
        cls.sari = cls._buat_pegawai('Sari', cls.unit_smp)

    def _buat_oleh(self, user, unit, **vals):
        return self._sebagai(self.env['hr.employee'], user).create(
            dict(vals, name='Tautan', company_id=unit.id))

    def test_tu_tautkan_kontak_wali_ditolak(self):
        self.assertTrue(self.wali.nti_edu_is_wali)
        with self.assertRaises(AccessError):
            self._buat_oleh(self.tu_smp, self.unit_smp, work_contact_id=self.wali.id)
        with self.assertRaises(AccessError):
            self._sebagai(self.sari, self.tu_smp).write({'work_contact_id': self.wali.id})
        self.assertNotEqual(self.sari.work_contact_id, self.wali)
        self.assertFalse(self.wali.employee_ids)

    def test_tu_tautkan_kontak_user_lain_ditolak(self):
        with self.assertRaises(AccessError):
            self._buat_oleh(self.tu_smp, self.unit_smp, work_contact_id=self.lain.partner_id.id)
        self.assertEqual(self.lain.email, 'lain@contoh.id')

    def test_tu_tautkan_siswa_unit_lain_ditolak(self):
        with self.assertRaises(AccessError):
            self._buat_oleh(self.tu_smp, self.unit_smp, work_contact_id=self.siswa_sma.id)
        # TU yang memegang unit siswa pun tidak boleh.
        with self.assertRaises(AccessError):
            self._buat_oleh(self.tu_dua, self.unit_sma, work_contact_id=self.siswa_sma.id)

    def test_hrd_tautkan_siswa_ditolak(self):
        with self.assertRaises(UserError):
            self._buat_oleh(self.hrd, self.unit_sma, work_contact_id=self.siswa_sma.id)
        with self.assertRaises(UserError):
            self._sebagai(self.sari, self.hrd).write({'work_contact_id': self.siswa_sma.id})
        self.assertFalse(self.siswa_sma.employee_ids)

    def test_hrd_tautkan_kontak_user_lain_ditolak(self):
        with self.assertRaises(UserError):
            self._buat_oleh(self.hrd, self.unit_sma, work_contact_id=self.lain.partner_id.id)
        with self.assertRaises(UserError):
            self._sebagai(self.sari, self.hrd).write({'work_contact_id': self.lain.partner_id.id})
        # Menautkan akun itu sendiri (user_id) tetap boleh bagi HRD.
        emp = self._buat_oleh(self.hrd, self.unit_sma, user_id=self.lain.id)
        self.assertEqual(emp.work_contact_id, self.lain.partner_id)

    def test_hrd_tautkan_wali_tanpa_akun_boleh(self):
        emp = self._buat_oleh(self.hrd, self.unit_smp, work_contact_id=self.wali.id)
        self.assertEqual(emp.work_contact_id, self.wali)
        self.assertTrue(self.wali.nti_edu_is_wali)

    def test_tu_isi_user_id_saat_buat_ditolak(self):
        with self.assertRaises(AccessError):
            self._buat_oleh(self.tu_smp, self.unit_smp, user_id=self.guru_smp.id)
        self.assertFalse(self.guru_smp.employee_ids)

    def test_penempatan_kontak_siswa_ditolak(self):
        # Hanya superuser yang bisa membuat keadaan ini; wizard tetap menolak dan tidak menyentuh kontak siswa.
        emp = self._buat_pegawai('Siswa Pegawai', self.unit_sma, work_contact_id=self.siswa_sma.id)
        wizard = self._sebagai(self.env['nti_edu.pegawai.penempatan.wizard'], self.hrd).create(
            {'employee_id': emp.id, 'company_id': self.unit_smp.id})
        with self.assertRaises(UserError):
            wizard.action_tempatkan()
        self.assertEqual(self.siswa_sma.company_id, self.unit_sma)


@tagged('post_install', '-at_install')
class TestProfilSaatBuat(_DasarReview):
    """Kritis 2: profil yang diisi saat membuat pegawai tersimpan di kontak kerja."""

    def test_tu_buat_dengan_profil(self):
        emp = self._sebagai(self.env['hr.employee'], self.tu_smp).create({
            'name': 'Baru TU', 'company_id': self.unit_smp.id,
            'nti_edu_nuptk': '5555', 'nti_edu_status_kepegawaian': 'pns',
            'nti_edu_sertifikasi_ids': [(0, 0, {'jenis': 'pendidik', 'nomor': 'S-BARU'})],
        })
        kontak = emp.sudo().work_contact_id
        self.assertEqual(kontak.nti_edu_nuptk, '5555')
        self.assertEqual(kontak.nti_edu_status_kepegawaian, 'pns')
        self.assertEqual(kontak.nti_edu_sertifikasi_ids.mapped('nomor'), ['S-BARU'])

    def test_hrd_dan_superuser_buat_dengan_profil(self):
        emp = self._sebagai(self.env['hr.employee'], self.hrd).create(
            {'name': 'Baru HRD', 'company_id': self.unit_smp.id, 'nti_edu_nuptk': '6666'})
        self.assertEqual(emp.sudo().work_contact_id.nti_edu_nuptk, '6666')
        emp2 = self._buat_pegawai('Baru SU', self.unit_sma, nti_edu_nip='7777', nti_edu_bidang_studi='Fisika')
        self.assertEqual(emp2.work_contact_id.nti_edu_nip, '7777')
        self.assertEqual(emp2.work_contact_id.nti_edu_bidang_studi, 'Fisika')

    def test_tu_buat_dengan_profil_dan_email(self):
        emp = self._sebagai(self.env['hr.employee'], self.tu_smp).create({
            'name': 'Baru Email', 'company_id': self.unit_smp.id, 'work_email': 'baru@contoh.id',
            'nti_edu_nik': '3201000000000201'})
        kontak = emp.sudo().work_contact_id
        self.assertEqual(kontak.email, 'baru@contoh.id')
        self.assertEqual(kontak.nti_edu_nik, '3201000000000201')

    def test_inverse_hanya_menulis_field_yang_berubah(self):
        sari = self._buat_pegawai('Sari', self.unit_smp, nti_edu_nip='1111')
        kontak = sari.work_contact_id
        Partner = type(self.env['res.partner'])
        asli = Partner.write
        tercatat = []

        def catat(rec, vals):
            if rec.ids == kontak.ids:
                tercatat.append(set(vals) & set(PROFIL_TERKAIT))
            return asli(rec, vals)

        self.patch(Partner, 'write', catat)
        self._sebagai(sari, self.tu_smp).write({'nti_edu_nuptk': '2222'})
        self.assertEqual(set().union(*tercatat), {'nti_edu_nuptk'})
        self.assertEqual(kontak.nti_edu_nip, '1111')
        self.assertEqual(kontak.nti_edu_nuptk, '2222')

    def test_sertifikasi_ke_kontak_baru_saat_ganti_kontak(self):
        sari = self._buat_pegawai('Sari', self.unit_smp)
        lama = sari.work_contact_id
        baru = self.env['res.partner'].create({'name': 'Sari Baru', 'company_id': self.unit_smp.id})
        self._sebagai(sari, self.hrd).write({
            'work_contact_id': baru.id,
            'nti_edu_sertifikasi_ids': [(0, 0, {'jenis': 'pendidik', 'nomor': 'S-PINDAH'})]})
        sert = self.env['nti_edu.pegawai.sertifikasi'].search([('nomor', '=', 'S-PINDAH')])
        self.assertEqual(sert.partner_id, baru)
        self.assertFalse(lama.nti_edu_sertifikasi_ids)


@tagged('post_install', '-at_install')
class TestEmailKerja(_DasarReview):
    """Penting 5: email/HP kerja disinkron ke kontak bersama lewat penjaga profil."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.budi_smp = cls._buat_pegawai('Budi', cls.unit_smp, work_email='budi@contoh.id')
        cls.budi_sma = cls._buat_pegawai('Budi', cls.unit_sma, work_contact_id=cls.budi_smp.work_contact_id.id)
        cls.sari = cls._buat_pegawai('Sari', cls.unit_smp, work_email='sari@contoh.id')

    def test_tu_satu_unit_ubah_email_orang_dua_unit_ditolak(self):
        with self.assertRaises(AccessError):
            self._sebagai(self.budi_smp, self.tu_smp).write({'work_email': 'curian@contoh.id'})
        self.assertEqual(self.budi_smp.work_contact_id.email, 'budi@contoh.id')
        with self.assertRaises(AccessError):
            self._sebagai(self.budi_smp, self.tu_smp).write({'mobile_phone': '0811'})
        self.assertFalse(self.budi_smp.work_contact_id.mobile)

    def test_tu_unit_sendiri_ubah_email_boleh(self):
        self._sebagai(self.sari, self.tu_smp).write({'work_email': 'sari.baru@contoh.id'})
        self.assertEqual(self.sari.work_contact_id.email, 'sari.baru@contoh.id')

    def test_tu_semua_unit_ubah_email_pegawai_berakun(self):
        smp, sma, user = self._dua_unit_berakun()
        self._sebagai(sma, self.tu_dua).write({'work_email': 'orang.baru@contoh.id'})
        self.assertEqual(user.email, 'orang.baru@contoh.id')
        self.assertEqual(smp.work_contact_id.email, 'orang.baru@contoh.id')

    def test_tu_tak_ubah_email_akun_hrd(self):
        pegawai = self._buat_pegawai(
            'Bu HRD', self.unit_smp, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        email = self.hrd.email
        with self.assertRaises(AccessError):
            self._sebagai(pegawai, self.tu_dua).write({'work_email': 'ambil@contoh.id'})
        self.assertEqual(self.hrd.email, email)

    def test_tu_tak_ubah_email_kontak_wali(self):
        wali = self.env['res.partner'].create({'name': 'Guru Wali', 'email': 'guruwali@contoh.id'})
        siswa = self.env['res.partner'].create(
            {'name': 'Anak Guru', 'nti_edu_is_siswa': True, 'company_id': self.unit_sma.id})
        self.env['nti_edu.siswa.wali'].create({'siswa_id': siswa.id, 'partner_id': wali.id})
        pegawai = self._buat_pegawai('Guru Wali', self.unit_smp, work_contact_id=wali.id)
        with self.assertRaises(AccessError):
            self._sebagai(pegawai, self.tu_dua).write({'work_email': 'lain@contoh.id'})
        self.assertEqual(wali.email, 'guruwali@contoh.id')

    # --- Akun ber-hak atau dengan unit di luar pegangan pemanggil: tidak lewat sudo ---

    def _pegawai_berakun(self, nama, unit, units, grup):
        """Pegawai di `unit` dengan akun ber-`grup` yang memegang `units`."""
        login = nama.lower().replace(' ', '_')
        pegawai = self._buat_pegawai(nama, unit, work_email=login + '@contoh.id')
        user = self._akun(pegawai, login, units, grup=grup)
        return pegawai, user

    def _ditolak(self, pegawai, pemanggil, user):
        email = user.email
        with self.assertRaises(AccessError):
            self._sebagai(pegawai, pemanggil).write({'work_email': 'penyerang@contoh.id'})
        self.assertEqual(user.email, email)

    def test_tu_tak_ubah_email_tu_lain(self):
        # Rekan TU dengan akun SMP+SMA tetapi data pegawai hanya di SMP; pemanggil hanya memegang SMP.
        pegawai, user = self._pegawai_berakun(
            'TU Rekan', self.unit_smp, self.unit_smp | self.unit_sma, 'nti_edu_pegawai.group_pegawai_operator')
        self._ditolak(pegawai, self.tu_smp, user)

    def test_tu_tak_ubah_email_operator_data_sekolah(self):
        pegawai, user = self._pegawai_berakun(
            'Operator Data', self.unit_smp, self.unit_smp, 'nti_edu_base.group_base_operator')
        self._ditolak(pegawai, self.tu_smp, user)

    def test_hrd_tak_ubah_email_tu(self):
        pegawai, user = self._pegawai_berakun(
            'TU Lain', self.unit_smp, self.unit_smp, 'nti_edu_pegawai.group_pegawai_operator')
        self._ditolak(pegawai, self.hrd, user)

    def test_tu_tak_ubah_email_akun_dengan_unit_di_luar_pegangannya(self):
        smk = self.env['res.company'].create({
            'name': 'SMK Email Tes', 'parent_id': self.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': self.env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'pgeml'})
        pegawai, user = self._pegawai_berakun(
            'Guru Luar', self.unit_smp, self.unit_smp | smk, 'nti_edu_base.group_base_pengguna')
        self._ditolak(pegawai, self.tu_dua, user)
        # HRD boleh untuk akun guru biasa, di unit mana pun.
        self._sebagai(pegawai, self.hrd).write({'work_email': 'guru.luar.baru@contoh.id'})
        self.assertEqual(user.email, 'guru.luar.baru@contoh.id')

    def test_tu_semua_unit_ubah_email_guru_biasa(self):
        pegawai, user = self._pegawai_berakun(
            'Guru Biasa', self.unit_smp, self.unit_smp, 'nti_edu_base.group_base_pengguna')
        self._sebagai(pegawai, self.tu_smp).write({'work_email': 'guru.biasa.baru@contoh.id'})
        self.assertEqual(user.email, 'guru.biasa.baru@contoh.id')

    def test_hrd_ubah_email_guru_biasa(self):
        smp, sma, user = self._dua_unit_berakun()
        self._sebagai(sma, self.hrd).write({'work_email': 'oleh.hrd@contoh.id'})
        self.assertEqual(user.email, 'oleh.hrd@contoh.id')


@tagged('post_install', '-at_install')
class TestAksesAkun(_DasarReview):
    """Penting 3, 4, 6 dan minor: akses akun saat arsip, aktif lagi, dan pengaktifan oleh HRD."""

    def test_aktifkan_lagi_mengembalikan_unit(self):
        smp, sma, user = self._dua_unit_berakun()
        sma_tu = self._sebagai(sma, self.tu_dua)
        sma_tu.action_archive()
        self.assertEqual(user.company_ids, self.unit_smp)
        sma_tu.action_unarchive()
        self.assertEqual(user.company_ids, self.unit_smp | self.unit_sma)
        self.assertTrue(user.active)

    def test_aktifkan_lagi_tak_menambah_unit_akun_hrd_oleh_tu(self):
        smp = self._buat_pegawai(
            'Bu HRD', self.unit_smp, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        sma = self._buat_pegawai(
            'Bu HRD', self.unit_sma, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        sma.write({'active': False})
        self.assertEqual(self.hrd.company_ids, self.unit_smp)
        self._sebagai(sma, self.tu_dua).write({'active': True})
        self.assertEqual(self.hrd.company_ids, self.unit_smp)

    def test_tu_tak_mencabut_unit_akun_hrd(self):
        smp = self._buat_pegawai(
            'Bu HRD', self.unit_smp, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        self._buat_pegawai(
            'Bu HRD', self.unit_sma, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        self._sebagai(smp, self.tu_smp).write({'active': False})
        self.assertEqual(self.hrd.company_ids, self.unit_smp | self.unit_sma)
        self.assertTrue(self.hrd.active)

    def test_arsip_terakhir_mencabut_unit_lalu_menonaktifkan(self):
        pegawai = self._buat_pegawai('Pak Akhir', self.unit_smp, work_email='akhir@contoh.id')
        user = self._akun(pegawai, 'pak_akhir', self.unit_smp | self.unit_sma)
        pegawai.write({'active': False})
        self.assertFalse(user.active)
        self.assertEqual(user.company_ids, self.unit_sma)
        self.assertEqual(user.company_id, self.unit_sma)

    def test_arsip_semua_sekaligus_menyisakan_satu_unit(self):
        smp, sma, user = self._dua_unit_berakun()
        (smp | sma).write({'active': False})
        self.assertFalse(user.active)
        self.assertEqual(len(user.company_ids), 1)
        self.assertEqual(user.company_ids, user.company_id)
        self.assertEqual(user.company_id, self.unit_smp)

    def test_sisa_pegawai_dicocokkan_lewat_kontak(self):
        smp = self._buat_pegawai('Pak Kontak', self.unit_smp, work_email='kontak@contoh.id')
        user = self._akun(smp, 'pak_kontak', self.unit_smp | self.unit_sma)
        # Record SMA milik orang yang sama tanpa user_id (mis. dibuat sebelum akun ada).
        sma = self._buat_pegawai('Pak Kontak', self.unit_sma, work_contact_id=smp.work_contact_id.id)
        self.assertFalse(sma.user_id)
        smp.write({'active': False})
        self.assertTrue(user.active)
        self.assertEqual(user.company_ids, self.unit_sma)

    def _akun_nonaktif(self):
        smp, sma, user = self._dua_unit_berakun()
        user.write({'company_ids': [(4, self.yayasan.id)]})
        (smp | sma).write({'active': False})
        self.assertFalse(user.active)
        return smp, sma, user

    def test_hrd_mengaktifkan_akun(self):
        smp, sma, user = self._akun_nonaktif()
        smp.write({'active': True})
        self.assertFalse(user.active)
        self._sebagai(smp, self.hrd).action_nti_edu_aktifkan_akun_login()
        self.assertTrue(user.active)
        self.assertEqual(user.company_ids, self.unit_smp | self.yayasan)
        self.assertEqual(user.company_id, self.unit_smp)

    def test_hrd_mengaktifkan_akun_dua_unit(self):
        smp, sma, user = self._akun_nonaktif()
        (smp | sma).write({'active': True})
        self._sebagai(sma, self.hrd).action_nti_edu_aktifkan_akun_login()
        self.assertTrue(user.active)
        self.assertEqual(user.company_ids, self.unit_smp | self.unit_sma | self.yayasan)
        self.assertIn(user.company_id, self.unit_smp | self.unit_sma)

    def test_tu_tak_bisa_mengaktifkan_akun(self):
        smp, sma, user = self._akun_nonaktif()
        smp.write({'active': True})
        with self.assertRaises(AccessError):
            self._sebagai(smp, self.tu_dua).action_nti_edu_aktifkan_akun_login()
        self.assertFalse(user.active)

    def test_penempatan_tak_menambah_unit_akun_hrd_oleh_tu(self):
        smp = self._buat_pegawai(
            'Bu HRD', self.unit_smp, work_contact_id=self.hrd.partner_id.id, user_id=self.hrd.id)
        self.hrd.write({'company_ids': [(3, self.unit_sma.id)], 'company_id': self.unit_smp.id})
        wizard = self._sebagai(self.env['nti_edu.pegawai.penempatan.wizard'], self.tu_dua).create(
            {'employee_id': smp.id, 'company_id': self.unit_sma.id})
        wizard.action_tempatkan()
        # Pegawai ditempatkan, tetapi TU tidak menambah unit ke akun HRD.
        self.assertEqual(self.hrd.company_ids, self.unit_smp)


@tagged('post_install', '-at_install')
class TestTampilanReview(_DasarReview):
    """Minor: tampilan sesuai hak (akun login, tombol aktifkan akun, hapus sertifikasi)."""

    def _form(self, user):
        view = self.env.ref('nti_edu_pegawai.view_pegawai_form')
        arch = self._sebagai(self.env['hr.employee'], user).get_views([(view.id, 'form')])['views']['form']['arch']
        return etree.fromstring(arch)

    def test_user_id_hanya_bisa_diubah_hrd(self):
        for user, bisa in ((self.tu_smp, False), (self.hrd, True)):
            form = self._form(user)
            medan = form.xpath('//page[@name="hr_settings"]//field[@name="user_id"]')
            self.assertTrue(medan)
            bisa_diubah = [f for f in medan if f.get('readonly') not in ('1', 'True', 'true')]
            self.assertEqual(bool(bisa_diubah), bisa, user.login)

    def test_tombol_aktifkan_akun_hanya_hrd(self):
        tombol = '//button[@name="action_nti_edu_aktifkan_akun_login"]'
        self.assertFalse(self._form(self.tu_smp).xpath(tombol))
        self.assertTrue(self._form(self.hrd).xpath(tombol))

    def test_hapus_sertifikasi_tersembunyi_bagi_tu(self):
        for user, hapus in ((self.tu_smp, False), (self.hrd, True)):
            daftar = self._form(user).xpath('//field[@name="nti_edu_sertifikasi_ids"]/list')
            self.assertEqual(len(daftar), 1, user.login)
            self.assertEqual(daftar[0].get('delete') not in ('0', 'false', 'False'), hapus, user.login)
