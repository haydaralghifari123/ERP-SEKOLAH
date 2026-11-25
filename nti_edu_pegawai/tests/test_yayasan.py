# -*- coding: utf-8 -*-
"""Staf yayasan sebagai pegawai (pilihan B): pegawai langsung di company yayasan, dikelola hanya oleh HRD."""
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import NtiPegawaiCommon

PESAN_YAYASAN = "staf yayasan hanya boleh dikelola HRD"


@tagged('post_install', '-at_install')
class TestYayasan(NtiPegawaiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # HRD memegang semua unit dan yayasannya.
        cls.hrd.write({'company_ids': [(4, cls.yayasan.id)]})
        operator = 'nti_edu_pegawai.group_pegawai_operator'
        # TU yang (keliru) juga diberi company yayasan: penjaga "siapa" tetap menolak.
        cls.tu_yys = cls._buat_user('peg_tu_yys', operator, cls.unit_smp | cls.yayasan)
        cls.tu_sma_yys = cls._buat_user('peg_tu_sma_yys', operator, cls.unit_sma | cls.yayasan)
        cls.staf = cls._buat_pegawai(
            'Bu Bendahara', cls.yayasan, nti_edu_jenis_ptk='staf_yayasan', work_email='bendahara@contoh.id')

    def _sebagai(self, rec, user):
        return rec.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def _akun(self, pegawai, login, companies):
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': pegawai.name, 'login': login, 'partner_id': pegawai.work_contact_id.id,
            'company_id': companies[0].id, 'company_ids': [(6, 0, companies.ids)],
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_pengguna').id])],
        })
        pegawai.write({'user_id': user.id})
        return user

    def _wizard(self, pegawai, user, tujuan):
        return self._sebagai(self.env['nti_edu.pegawai.penempatan.wizard'], user).create(
            {'employee_id': pegawai.id, 'company_id': tujuan.id})

    def _di(self, pegawai, company):
        return self.env['hr.employee'].with_context(active_test=False).search([
            ('work_contact_id', '=', pegawai.work_contact_id.id), ('company_id', '=', company.id)])

    def _guru_sma_dan_yayasan(self, login=None):
        """Guru SMA yang juga staf yayasan (satu kontak, dua penempatan); berakun bila `login` diberikan."""
        sma = self._buat_pegawai('Pak Guru Yayasan', self.unit_sma, work_email='guruyys@contoh.id')
        user = self._akun(sma, login, self.unit_sma | self.yayasan) if login else self.env['res.users']
        yys = self._buat_pegawai(
            'Pak Guru Yayasan', self.yayasan, work_contact_id=sma.work_contact_id.id,
            nti_edu_jenis_ptk='staf_yayasan', **({'user_id': user.id} if user else {}))
        return sma, yys, user

    # --- Membuat dan mengubah data pegawai yayasan ---

    def test_hrd_buat_staf_yayasan(self):
        self.assertIn('staf_yayasan', dict(self.env['hr.employee']._fields['nti_edu_jenis_ptk'].selection))
        emp = self._sebagai(self.env['hr.employee'], self.hrd).create({
            'name': 'Pak Pengurus', 'company_id': self.yayasan.id, 'nti_edu_jenis_ptk': 'staf_yayasan',
            'nti_edu_nuptk': '7700000000000001'})
        self.assertEqual(emp.company_id, self.yayasan)
        self.assertEqual(emp.nti_edu_jenis_ptk, 'staf_yayasan')
        self.assertEqual(emp.sudo().work_contact_id.nti_edu_nuptk, '7700000000000001')
        # HRD juga boleh mengubah dan mengarsipkan staf yayasan.
        staf = self._sebagai(self.staf, self.hrd)
        staf.write({'nti_edu_tmt': '2026-07-01', 'nti_edu_nip': '7700000000000002'})
        self.assertEqual(self.staf.work_contact_id.nti_edu_nip, '7700000000000002')
        staf.action_archive()
        self.assertFalse(self.staf.active)

    def test_tu_tak_bisa_buat_atau_ubah_pegawai_yayasan(self):
        Emp = self._sebagai(self.env['hr.employee'], self.tu_yys)
        jumlah = self.env['hr.employee'].search_count([('company_id', '=', self.yayasan.id)])
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            Emp.create({'name': 'Staf Titipan', 'company_id': self.yayasan.id})
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            Emp.with_context(allowed_company_ids=[self.yayasan.id, self.unit_smp.id]).create(
                {'name': 'Staf Bawaan'})
        self.assertEqual(self.env['hr.employee'].search_count([('company_id', '=', self.yayasan.id)]), jumlah)
        staf = self._sebagai(self.staf, self.tu_yys)
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            staf.write({'nti_edu_tmt': '2026-07-01'})
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            staf.action_archive()
        self.assertTrue(self.staf.active)
        self.assertFalse(self.staf.nti_edu_tmt)
        # Mengaktifkan lagi staf yayasan yang diarsip juga hanya HRD.
        self.staf.action_archive()
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            staf.action_unarchive()
        self.assertFalse(self.staf.active)
        # Memindahkan pegawai unit ke yayasan lewat company_id pun ditolak.
        guru = self._buat_pegawai('Pak Unit', self.unit_smp)
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            self._sebagai(guru, self.tu_yys).write({'company_id': self.yayasan.id})
        self.assertEqual(guru.company_id, self.unit_smp)
        # Pegawai unit biasa tetap bisa dikelola TU-nya.
        self._sebagai(guru, self.tu_yys).write({'nti_edu_tmt': '2026-07-13'})
        self.assertEqual(str(guru.nti_edu_tmt), '2026-07-13')

    def test_tu_tak_bisa_tautkan_kontak_staf_yayasan(self):
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            self._sebagai(self.env['hr.employee'], self.tu_yys).create({
                'name': 'Bu Bendahara', 'company_id': self.unit_smp.id,
                'work_contact_id': self.staf.work_contact_id.id})
        self.assertEqual(len(self.staf.work_contact_id.employee_ids), 1)

    def test_profil_orang_berpenempatan_yayasan_hanya_hrd(self):
        sma, yys, user = self._guru_sma_dan_yayasan()
        kontak = sma.work_contact_id
        for tu in (self.tu_dua, self.tu_sma_yys):
            with self.assertRaises(AccessError):
                self._sebagai(sma, tu).write({'nti_edu_nuptk': '7700000000000003'})
            with self.assertRaises(AccessError):
                self._sebagai(sma, tu).write({'work_email': 'curian@contoh.id'})
            with self.assertRaises(AccessError):
                self._sebagai(self.env['nti_edu.pegawai.sertifikasi'], tu).create(
                    {'partner_id': kontak.id, 'nomor': 'S-YYS'})
        self.assertFalse(kontak.nti_edu_nuptk)
        self.assertEqual(kontak.email, 'guruyys@contoh.id')
        self.assertFalse(self._sebagai(kontak, self.tu_sma_yys)._nti_edu_boleh_ubah_profil_pegawai())
        # Data per penempatan di unit tetap milik TU unitnya.
        self._sebagai(sma, self.tu_sma).write({'nti_edu_jenis_ptk': 'guru_mapel'})
        self.assertEqual(sma.nti_edu_jenis_ptk, 'guru_mapel')
        self._sebagai(sma, self.hrd).write({'nti_edu_nuptk': '7700000000000003'})
        self.assertEqual(kontak.nti_edu_nuptk, '7700000000000003')
        # Setelah penempatan yayasan diarsipkan, TU SMA kembali memegang semua penempatan aktifnya.
        yys.write({'active': False})
        self._sebagai(sma, self.tu_sma).write({'nti_edu_bidang_studi': 'Fisika'})
        self.assertEqual(kontak.nti_edu_bidang_studi, 'Fisika')

    # --- Penempatan ke/dari yayasan ---

    def test_hrd_tempatkan_ke_yayasan(self):
        guru = self._buat_pegawai('Pak Pengurus Baru', self.unit_smp, work_email='pengurus@contoh.id')
        user = self._akun(guru, 'pak_pengurus', self.unit_smp)
        wizard = self._wizard(guru, self.hrd, self.yayasan)
        self.assertIn(self.yayasan, wizard.company_ids_diizinkan)
        self.assertIn(self.unit_sma, wizard.company_ids_diizinkan)
        aksi = wizard.action_tempatkan()
        baru = self._di(guru, self.yayasan)
        self.assertEqual(len(baru), 1)
        self.assertEqual(aksi['res_id'], baru.id)
        self.assertEqual(baru.user_id, user)
        self.assertEqual(user.company_ids, self.unit_smp | self.yayasan)
        self.assertTrue(user.active)

    def test_hrd_tempatkan_dari_yayasan_ke_unit(self):
        wizard = self._wizard(self.staf, self.hrd, self.unit_sma)
        self.assertEqual(wizard.company_ids_diizinkan, self.unit_smp | self.unit_sma)
        wizard.action_tempatkan()
        self.assertEqual(len(self._di(self.staf, self.unit_sma)), 1)

    def test_hrd_tak_tempatkan_ke_yayasan_lain(self):
        lain = self.env['res.company'].create({'name': 'Yayasan Lain Tes', 'nti_edu_jenis': 'yayasan'})
        self.hrd.write({'company_ids': [(4, lain.id)]})
        guru = self._buat_pegawai('Pak Lintas', self.unit_smp)
        wizard = self._wizard(guru, self.hrd, lain)
        self.assertNotIn(lain, wizard.company_ids_diizinkan)
        with self.assertRaises(AccessError):
            wizard.action_tempatkan()
        self.assertFalse(self._di(guru, lain))

    def test_tu_tak_bisa_tempatkan_ke_yayasan(self):
        guru = self._buat_pegawai('Pak Titip', self.unit_smp)
        for tu in (self.tu_smp, self.tu_dua, self.tu_yys):
            wizard = self._wizard(guru, tu, self.yayasan)
            self.assertNotIn(self.yayasan, wizard.company_ids_diizinkan)
            with self.assertRaises(AccessError):
                wizard.action_tempatkan()
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            self._wizard(guru, self.tu_yys, self.yayasan).action_tempatkan()
        self.assertFalse(self._di(guru, self.yayasan))
        # Dari yayasan ke unit pun hanya HRD.
        wizard = self._wizard(self.staf, self.tu_yys, self.unit_smp)
        self.assertFalse(wizard.company_ids_diizinkan)
        with self.assertRaisesRegex(AccessError, PESAN_YAYASAN):
            wizard.action_tempatkan()
        self.assertFalse(self._di(self.staf, self.unit_smp))

    # --- Akses akun ---

    def test_arsip_penempatan_yayasan_mencabut_yayasan(self):
        sma, yys, user = self._guru_sma_dan_yayasan('guru_yys')
        self.assertEqual(user.company_ids, self.unit_sma | self.yayasan)
        self._sebagai(yys, self.hrd).action_archive()
        self.assertEqual(user.company_ids, self.unit_sma)
        self.assertTrue(user.active)
        # Diaktifkan lagi oleh HRD: yayasan kembali ke akun.
        self._sebagai(yys, self.hrd).action_unarchive()
        self.assertEqual(user.company_ids, self.unit_sma | self.yayasan)

    def test_tu_arsip_unit_tak_mencabut_yayasan(self):
        sma, yys, user = self._guru_sma_dan_yayasan('guru_yys2')
        self._sebagai(sma, self.tu_sma_yys).action_archive()
        self.assertEqual(user.company_ids, self.yayasan)
        self.assertTrue(user.active)

    def test_tu_tak_menonaktifkan_akun_yang_memegang_yayasan(self):
        # Yayasan diberikan administrator tanpa data pegawai yayasan: TU tidak mencabutnya dan tidak menonaktifkan.
        guru = self._buat_pegawai('Pak Akses Yayasan', self.unit_smp, work_email='aksesyys@contoh.id')
        user = self._akun(guru, 'akses_yys', self.unit_smp | self.yayasan)
        self._sebagai(guru, self.tu_yys).action_archive()
        self.assertTrue(user.active)
        self.assertEqual(user.company_ids, self.yayasan)
        self.assertEqual(user.company_id, self.yayasan)

    def test_arsip_staf_yayasan_terakhir_lalu_hrd_aktifkan_akun(self):
        user = self._akun(self.staf, 'bendahara', self.yayasan)
        self._sebagai(self.staf, self.hrd).action_archive()
        self.assertFalse(user.active)
        self._sebagai(self.staf, self.hrd).action_unarchive()
        self.assertFalse(user.active)
        self._sebagai(self.staf, self.hrd).action_nti_edu_aktifkan_akun_login()
        self.assertTrue(user.active)
        self.assertEqual(user.company_ids, self.yayasan)
        self.assertEqual(user.company_id, self.yayasan)

    def test_hrd_aktifkan_akun_mencabut_yayasan_tanpa_penempatan_aktif(self):
        sma, yys, user = self._guru_sma_dan_yayasan('guru_yys3')
        (sma | yys).write({'active': False})
        self.assertFalse(user.active)
        # Keadaan lama: yayasan masih tersisa di akun walau penempatan yayasannya diarsip.
        user.write({'company_ids': [(4, self.yayasan.id)]})
        sma.write({'active': True})
        self._sebagai(sma, self.hrd).action_nti_edu_aktifkan_akun_login()
        self.assertTrue(user.active)
        self.assertEqual(user.company_ids, self.unit_sma)

    def test_buat_akun_staf_yayasan(self):
        with self.assertRaises(AccessError):
            self._sebagai(self.env['nti_edu.pegawai.akun.wizard'], self.tu_yys).create(
                {'employee_id': self.staf.id}).action_buat()
        self.assertFalse(self.staf.user_id)
        wizard = self._sebagai(self.env['nti_edu.pegawai.akun.wizard'], self.hrd).create(
            {'employee_id': self.staf.id})
        self.assertEqual(wizard.login, 'bendahara@contoh.id')
        wizard.action_buat()
        user = self.staf.user_id
        self.assertTrue(user)
        self.assertEqual(user.company_ids, self.yayasan)
        self.assertEqual(user.company_id, self.yayasan)
        self.assertEqual(user.partner_id, self.staf.work_contact_id)

    # --- Jenis company ---

    def test_jenis_company_berpegawai_tak_bisa_diubah(self):
        unit = self.env['res.company'].create({
            'name': 'SMK Jenis Yayasan', 'parent_id': self.yayasan.id, 'nti_edu_jenis': 'unit',
            'nti_edu_jenjang_id': self.env.ref('nti_edu_base.jenjang_sma').id, 'nti_edu_kode': 'pgjny'})
        guru = self._buat_pegawai('Pak SMK', unit)
        with self.assertRaises(ValidationError):
            unit.write({'nti_edu_jenis': 'yayasan'})
        self.assertEqual(unit.nti_edu_jenis, 'unit')
        yayasan2 = self.env['res.company'].create({'name': 'Yayasan Jenis Tes', 'nti_edu_jenis': 'yayasan'})
        staf2 = self._buat_pegawai('Pak Pengurus Dua', yayasan2, nti_edu_jenis_ptk='staf_yayasan')
        with self.assertRaises(ValidationError):
            yayasan2.write({'nti_edu_jenis': 'unit'})
        self.assertEqual(yayasan2.nti_edu_jenis, 'yayasan')
        # Menulis jenis yang sama bukan perubahan; tanpa pegawai aktif jenis boleh diganti.
        unit.write({'nti_edu_jenis': 'unit'})
        yayasan2.write({'nti_edu_jenis': 'yayasan'})
        (guru | staf2).write({'active': False})
        unit.write({'nti_edu_jenis': 'yayasan'})
        yayasan2.write({'nti_edu_jenis': 'unit'})
        self.assertEqual(unit.nti_edu_jenis, 'yayasan')
        self.assertEqual(yayasan2.nti_edu_jenis, 'unit')
