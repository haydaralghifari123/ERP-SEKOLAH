# -*- coding: utf-8 -*-
import base64
from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged

from .common import NtiTagihanCommon

# Isi berkas minimal dengan tanda awal (magic bytes) yang benar.
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
PDF = b'%PDF-1.4\n%tes\n'


@tagged('post_install', '-at_install')
class TestKonfirmasi(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Move = cls.env['account.move']
        cls.Konfirmasi = cls.env['nti_edu.tagihan.konfirmasi']
        cls.Mesin = cls.env['nti_edu.tagihan.mesin']
        cls.spp = cls._buat_komponen('SPP Konfirmasi', 'periode_bulanan')
        cls.rekening_smp = cls._buat_rekening(cls.unit_smp)
        cls.rekening_sma = cls._buat_rekening(cls.unit_sma)
        cls.lainnya = cls.env.ref('nti_edu_tagihan.alasan_tolak_lainnya')
        cls.tidak_terbaca = cls.env.ref('nti_edu_tagihan.alasan_tolak_tidak_terbaca')

    # --- bantuan ---------------------------------------------------------------------------

    def _terbitkan(self, siswa=None, periode=date(2026, 8, 1), nominal=200000):
        return self.Move._nti_edu_terbitkan(
            siswa or self.siswa_a, self.spp, nominal, periode, periode + timedelta(days=9), periode=periode)

    def _vals(self, rekening=None, **vals):
        return dict({
            'tanggal_transfer': date(2026, 8, 5),
            'nominal': 200000,
            'rekening_id': (rekening or self.rekening_smp).id,
            'nama_rekening_pengirim': 'Wali X',
            'bukti': base64.b64encode(PNG),
            'bukti_nama': 'bukti.PNG',
            'catatan': 'SPP Agustus',
        }, **vals)

    def _kirim(self, tagihan, user=None, **vals):
        return self.Konfirmasi._buat_dari_portal(user or self.user_wali_x, tagihan.ids, self._vals(**vals))

    def _email(self, konfirmasi, template_xmlid):
        template = self.env.ref(template_xmlid)
        return self.env['mail.mail'].search([
            ('model', '=', konfirmasi._name), ('res_id', '=', konfirmasi.id),
            ('subject', '=', template._render_field('subject', konfirmasi.ids)[konfirmasi.id]),
        ])

    def _tolak(self, konfirmasi, user, alasan, catatan=False):
        wizard = self.env['nti_edu.tagihan.tolak.wizard'].with_user(user).create({
            'konfirmasi_id': konfirmasi.id, 'alasan_id': alasan.id, 'catatan': catatan})
        return wizard.action_tolak()

    # --- terima --------------------------------------------------------------------------------

    def test_buat_valid_dan_terima(self):
        spp = self._terbitkan()
        self.assertFalse(spp.nti_edu_menunggu_verifikasi)
        konf = self._kirim(spp)
        self.assertEqual(konf.state, 'menunggu')
        self.assertTrue(konf.name.startswith('KT/'))
        self.assertEqual(konf.pengirim_id, self.wali_x)
        self.assertEqual(konf.company_id, self.unit_smp)
        self.assertEqual(konf.siswa_ids, self.siswa_a)
        self.assertEqual(konf.bukti_nama, 'bukti.PNG')
        self.assertTrue(konf.bukti_is_gambar)
        spp.invalidate_recordset(['nti_edu_menunggu_verifikasi'])
        self.assertTrue(spp.nti_edu_menunggu_verifikasi)
        self.assertIn(spp, self.Move.search([('nti_edu_menunggu_verifikasi', '=', True)]))

        # Bendahara unit melihat antreannya; pemantau hanya membaca.
        self.assertIn(konf, self.Konfirmasi.with_user(self.bendahara_smp).search([('state', '=', 'menunggu')]))
        self.assertEqual(self.Konfirmasi.with_user(self.pemantau_smp).browse(konf.id).nominal, 200000)
        with self.assertRaises(AccessError):
            konf.with_user(self.pemantau_smp).action_terima()
        with self.assertRaises(AccessError):
            konf.with_user(self.pemantau_smp).write({'nominal_diterima': 1})

        konf.with_user(self.bendahara_smp).action_terima()
        self.assertEqual(konf.state, 'diterima')
        self.assertEqual(konf.diverifikasi_oleh_id, self.bendahara_smp)
        self.assertTrue(konf.tanggal_verifikasi)
        self.assertEqual(konf.nominal_diterima, 200000)
        self.assertEqual(len(konf.payment_ids), 1)
        payment = konf.payment_ids
        self.assertEqual(payment.amount, 200000)
        self.assertEqual(payment.partner_id, self.siswa_a)
        self.assertEqual(payment.date, date(2026, 8, 5))
        self.assertEqual(payment.journal_id, self.rekening_smp.journal_id)
        self.assertEqual(payment.memo, konf.name)
        self.assertTrue(spp.nti_edu_lunas)
        spp.invalidate_recordset(['nti_edu_menunggu_verifikasi'])
        self.assertFalse(spp.nti_edu_menunggu_verifikasi)

        email = self._email(konf, 'nti_edu_tagihan.mail_template_konfirmasi_diterima')
        self.assertEqual(len(email), 1)
        self.assertEqual(email.recipient_ids, self.wali_x)
        self.assertIn(self.siswa_a.name, email.body_html)
        self.assertIn(konf.name, email.body_html)

        # Sudah diterima: tidak bisa diterima ulang atau diubah.
        with self.assertRaises(UserError):
            konf.with_user(self.bendahara_smp).action_terima()
        with self.assertRaises(UserError):
            konf.with_user(self.bendahara_smp).write({'nominal_diterima': 1})

    def test_terima_nominal_dikoreksi(self):
        spp = self._terbitkan()
        konf = self._kirim(spp)
        konf.with_user(self.bendahara_smp).write({'nominal_diterima': 150000})
        konf.with_user(self.bendahara_smp).action_terima()
        self.assertEqual(konf.payment_ids.amount, 150000)
        self.assertEqual(spp.amount_residual, 50000)
        self.assertFalse(spp.nti_edu_lunas)

    def test_bendahara_hanya_ubah_nominal_diterima(self):
        spp = self._terbitkan()
        konf = self._kirim(spp)
        for vals in ({'state': 'diterima'}, {'nominal': 1}, {'payment_ids': [(6, 0, [])]},
                     {'tagihan_ids': [(6, 0, [])]}):
            with self.assertRaises(UserError):
                konf.with_user(self.bendahara_smp).write(vals)
        self.assertEqual(konf.state, 'menunggu')

    def test_tagihan_dibayar_tunai_sebelum_verifikasi(self):
        spp = self._terbitkan()
        konf = self._kirim(spp)
        self.Mesin.with_user(self.bendahara_smp)._bayar(spp, 200000, self.rekening_smp, date(2026, 8, 6), 'Tunai')
        self.assertTrue(spp.nti_edu_lunas)
        konf.with_user(self.bendahara_smp).action_terima()
        self.assertEqual(konf.state, 'diterima')
        self.assertEqual(konf.payment_ids.amount, 200000)
        self.assertEqual(konf.payment_ids.partner_id, self.siswa_a)
        self.siswa_a.invalidate_recordset(['nti_edu_saldo_kredit'])
        self.assertEqual(self.siswa_a.nti_edu_saldo_kredit, 200000)

    def test_dua_anak_satu_unit_kelebihan(self):
        # Siswa B (SMP) juga anak wali X untuk tes ini; kelebihan menjadi kredit siswa pertama menurut nama.
        self.env['nti_edu.siswa.wali'].create({
            'siswa_id': self.siswa_b.id, 'partner_id': self.wali_x.id, 'hubungan': 'ayah'})
        spp_a = self._terbitkan()
        spp_b = self._terbitkan(siswa=self.siswa_b)
        konf = self._kirim(spp_a | spp_b, nominal=450000)
        self.assertEqual(konf.siswa_ids, self.siswa_a | self.siswa_b)
        konf.with_user(self.bendahara_smp).action_terima()
        self.assertEqual(len(konf.payment_ids), 2)
        self.assertTrue(spp_a.nti_edu_lunas)
        self.assertTrue(spp_b.nti_edu_lunas)
        self.siswa_a.invalidate_recordset(['nti_edu_saldo_kredit'])
        self.assertEqual(self.siswa_a.nti_edu_saldo_kredit, 50000)

    # --- tolak ---------------------------------------------------------------------------------

    def test_tolak(self):
        spp = self._terbitkan()
        konf = self._kirim(spp)
        with self.assertRaises(UserError) as galat:
            self._tolak(konf, self.bendahara_smp, self.lainnya)
        self.assertIn('catatan', str(galat.exception).lower())
        self.assertEqual(konf.state, 'menunggu')
        with self.assertRaises(AccessError):
            self._tolak(konf, self.pemantau_smp, self.tidak_terbaca)

        self._tolak(konf, self.bendahara_smp, self.lainnya, 'Nama rekening tidak sesuai')
        self.assertEqual(konf.state, 'ditolak')
        self.assertEqual(konf.alasan_tolak_id, self.lainnya)
        self.assertEqual(konf.catatan_tolak, 'Nama rekening tidak sesuai')
        self.assertEqual(konf.diverifikasi_oleh_id, self.bendahara_smp)
        self.assertFalse(konf.payment_ids)
        self.assertFalse(spp.nti_edu_lunas)
        spp.invalidate_recordset(['nti_edu_menunggu_verifikasi'])
        self.assertFalse(spp.nti_edu_menunggu_verifikasi)

        email = self._email(konf, 'nti_edu_tagihan.mail_template_konfirmasi_ditolak')
        self.assertEqual(len(email), 1)
        self.assertEqual(email.recipient_ids, self.wali_x)
        self.assertIn(self.lainnya.name, email.body_html)
        self.assertIn('Nama rekening tidak sesuai', email.body_html)

        # Konfirmasi ditolak tidak dapat diubah siapa pun, juga lewat sudo.
        with self.assertRaises(UserError):
            konf.with_user(self.bendahara_smp).write({'nominal': 100000})
        with self.assertRaises(UserError):
            konf.sudo().write({'nominal': 100000})
        with self.assertRaises(UserError):
            konf.with_user(self.bendahara_smp).action_terima()
        with self.assertRaises(UserError):
            self._tolak(konf, self.bendahara_smp, self.tidak_terbaca)
        self.assertEqual(konf.nominal, 200000)

    def test_tolak_tanpa_catatan_bila_tidak_wajib(self):
        konf = self._kirim(self._terbitkan())
        self._tolak(konf, self.bendahara_smp, self.tidak_terbaca)
        self.assertEqual(konf.state, 'ditolak')
        self.assertFalse(konf.catatan_tolak)

    def test_tombol_tolak_membuka_wizard(self):
        konf = self._kirim(self._terbitkan())
        aksi = konf.with_user(self.bendahara_smp).action_tolak()
        self.assertEqual(aksi['res_model'], 'nti_edu.tagihan.tolak.wizard')
        wizard = Form(self.env['nti_edu.tagihan.tolak.wizard'].with_user(self.bendahara_smp).with_context(
            aksi['context']))
        self.assertEqual(wizard.konfirmasi_id, konf)
        wizard.alasan_id = self.tidak_terbaca
        wizard.save().action_tolak()
        self.assertEqual(konf.state, 'ditolak')

    def test_pengirim_tanpa_email(self):
        self.wali_x.email = False
        konf = self._kirim(self._terbitkan())
        konf.with_user(self.bendahara_smp).action_terima()
        self.assertEqual(konf.state, 'diterima')
        self.assertFalse(self._email(konf, 'nti_edu_tagihan.mail_template_konfirmasi_diterima'))
        self.assertTrue(konf.message_ids.filtered(lambda m: 'tidak dikirim' in (m.body or '')))

    # --- validasi server -----------------------------------------------------------------------

    def test_server_menolak(self):
        spp_a = self._terbitkan()
        spp_b = self._terbitkan(siswa=self.siswa_b)
        spp_c = self._terbitkan(siswa=self.siswa_c)
        # Tagihan anak orang lain (nama tagihan tidak bocor dalam pesan).
        with self.assertRaises(UserError) as galat:
            self._kirim(spp_b)
        self.assertNotIn(spp_b.name, str(galat.exception))
        with self.assertRaises(UserError):
            self._kirim(spp_a | spp_b)
        # Anak wali X lintas unit dalam satu konfirmasi.
        with self.assertRaises(UserError) as galat:
            self._kirim(spp_a | spp_c)
        self.assertIn('satu unit', str(galat.exception))
        # Berkas: jenis salah, isi tidak cocok ekstensi, terlalu besar, kosong.
        with self.assertRaises(UserError):
            self._kirim(spp_a, bukti=base64.b64encode(b'MZ\x90\x00'), bukti_nama='bukti.exe')
        with self.assertRaises(UserError):
            self._kirim(spp_a, bukti=base64.b64encode(b'MZ\x90\x00'), bukti_nama='bukti.png')
        with self.assertRaises(UserError):
            self._kirim(spp_a, bukti=False)
        self.unit_smp.nti_edu_bukti_ukuran_maks_mb = 1
        besar = PDF + b'0' * (1024 * 1024)
        with self.assertRaises(UserError) as galat:
            self._kirim(spp_a, bukti=base64.b64encode(besar), bukti_nama='bukti.pdf')
        self.assertIn('1 MB', str(galat.exception))
        konf = self._kirim(spp_a, bukti=base64.b64encode(PDF), bukti_nama='Bukti Transfer.PDF')
        self.assertFalse(konf.bukti_is_gambar)
        # Rekening unit lain, nominal nol.
        with self.assertRaises(UserError):
            self._kirim(spp_a, rekening=self.rekening_sma)
        with self.assertRaises(UserError):
            self._kirim(spp_a, nominal=0)
        # Tagihan lunas atau dibatalkan.
        self.Mesin._bayar(spp_a, 200000, self.rekening_smp, date(2026, 8, 6), 'Tunai')
        with self.assertRaises(UserError):
            self._kirim(spp_a)
        spp_sep = self._terbitkan(periode=date(2026, 9, 1))
        spp_sep._nti_edu_batalkan('Salah terbit')
        with self.assertRaises(UserError):
            self._kirim(spp_sep)
        with self.assertRaises(UserError):
            self.Konfirmasi._buat_dari_portal(self.user_wali_x, [], self._vals())

    def test_anak_nonaktif_tetap_bisa_konfirmasi(self):
        spp = self._terbitkan()
        self.siswa_a.nti_edu_status = 'lulus'
        konf = self._kirim(spp)
        self.assertEqual(konf.state, 'menunggu')

    def test_siswa_portal_sendiri(self):
        spp = self._terbitkan(siswa=self.siswa_b)
        user_siswa = self.env['res.users'].create({
            'login': 'tg_siswa_b', 'partner_id': self.siswa_b.id,
            'company_id': self.unit_smp.id, 'company_ids': [(6, 0, self.unit_smp.ids)],
            'groups_id': [(6, 0, self.env.ref('base.group_portal').ids)]})
        konf = self._kirim(spp, user=user_siswa)
        self.assertEqual(konf.pengirim_id, self.siswa_b)

    # --- isolasi -------------------------------------------------------------------------------

    def test_isolasi(self):
        konf = self._kirim(self._terbitkan())
        self.assertFalse(self.Konfirmasi.with_user(self.bendahara_sma).search([('id', '=', konf.id)]))
        with self.assertRaises(AccessError):
            konf.with_user(self.bendahara_sma).action_terima()
        with self.assertRaises(AccessError):
            self._tolak(konf, self.bendahara_sma, self.tidak_terbaca)
        # Portal tidak punya hak langsung atas model konfirmasi.
        with self.assertRaises(AccessError):
            self.Konfirmasi.with_user(self.user_wali_x).search([])
        self.assertEqual(konf.state, 'menunggu')
        # Admin keuangan semua unit boleh memverifikasi.
        konf.with_user(self.admin_keu).action_terima()
        self.assertEqual(konf.state, 'diterima')

    # --- penerima email tagihan ----------------------------------------------------------------

    def test_penerima_tagihan(self):
        SiswaWali = self.env['nti_edu.siswa.wali']
        ibu = self.env['res.partner'].create({'name': 'Ibu B', 'email': 'ibu.b@example.com'})
        ayah = self.env['res.partner'].create({'name': 'Ayah B'})
        self.assertFalse(self.siswa_b._nti_edu_penerima_tagihan())
        baris_ayah = SiswaWali.create({
            'siswa_id': self.siswa_b.id, 'partner_id': ayah.id, 'hubungan': 'ayah', 'is_penanggung_biaya': True})
        SiswaWali.create({
            'siswa_id': self.siswa_b.id, 'partner_id': ibu.id, 'hubungan': 'ibu', 'is_kontak_utama': True})
        # Penanggung biaya tanpa email → kontak utama ber-email.
        self.assertEqual(self.siswa_b._nti_edu_penerima_tagihan(), ibu)
        ayah.email = 'ayah.b@example.com'
        self.assertEqual(self.siswa_b._nti_edu_penerima_tagihan(), ayah)
        baris_ayah.is_penanggung_biaya = False
        ibu.email = False
        self.assertFalse(self.siswa_b._nti_edu_penerima_tagihan())
        self.assertEqual(self.siswa_a._nti_edu_penerima_tagihan(), self.wali_x)
