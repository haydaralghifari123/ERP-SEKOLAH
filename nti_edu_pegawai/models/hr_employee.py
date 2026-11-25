# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .res_partner import GRUP_HRD, GRUP_OPERATOR

# Field profil per orang yang dicerminkan (dapat diedit) pada form pegawai.
PROFIL_TERKAIT = (
    'nti_edu_nik', 'nti_edu_nuptk', 'nti_edu_nip', 'nti_edu_status_kepegawaian',
    'nti_edu_pendidikan_terakhir', 'nti_edu_bidang_studi',
)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    nti_edu_jenis_ptk = fields.Selection([
        ('guru_mapel', 'Guru Mapel'), ('guru_kelas', 'Guru Kelas'), ('guru_bk', 'Guru BK'),
        ('kepala_sekolah', 'Kepala Sekolah'), ('wakil_kepala', 'Wakil Kepala'),
        ('tendik_admin', 'Tenaga Administrasi'), ('pustakawan', 'Pustakawan'),
        ('laboran', 'Laboran'), ('lainnya', 'Lainnya'),
    ], string='Jenis PTK')
    nti_edu_tmt = fields.Date(string='TMT di Unit Ini')

    # Profil per orang: disimpan pada kontak kerja (satu per orang, terlihat di semua unit).
    nti_edu_nik = fields.Char(
        string='NIK', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil', groups=GRUP_OPERATOR)
    nti_edu_nuptk = fields.Char(
        string='NUPTK', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil', groups=GRUP_OPERATOR)
    nti_edu_nip = fields.Char(
        string='NIP', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil', groups=GRUP_OPERATOR)
    nti_edu_status_kepegawaian = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['nti_edu_status_kepegawaian'].selection,
        string='Status Kepegawaian', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil',
        groups=GRUP_OPERATOR)
    nti_edu_pendidikan_terakhir = fields.Selection(
        selection=lambda self: self.env['res.partner']._fields['nti_edu_pendidikan_terakhir'].selection,
        string='Pendidikan Terakhir', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil',
        groups=GRUP_OPERATOR)
    nti_edu_bidang_studi = fields.Char(
        string='Bidang Studi', compute='_compute_nti_edu_profil', inverse='_inverse_nti_edu_profil',
        groups=GRUP_OPERATOR)
    # Sertifikasi milik orangnya (kontak kerja); tulis lewat sini tetap melewati penjaga sertifikasi/kontak.
    nti_edu_sertifikasi_ids = fields.One2many(
        related='work_contact_id.nti_edu_sertifikasi_ids', readonly=False, groups=GRUP_OPERATOR,
        string='Sertifikasi')
    # Penanda tombol Aktifkan Akun Login (HRD): akun tertaut tetapi nonaktif.
    nti_edu_akun_nonaktif = fields.Boolean(
        string='Akun Login Nonaktif', compute='_compute_nti_edu_akun_nonaktif', groups=GRUP_OPERATOR)

    @api.depends('user_id')
    def _compute_nti_edu_akun_nonaktif(self):
        for rec in self:
            user = rec.sudo().user_id
            rec.nti_edu_akun_nonaktif = bool(user) and not user.active

    @api.constrains('company_id')
    def _check_nti_edu_pegawai_unit(self):
        for rec in self.sudo():
            if rec.company_id.nti_edu_jenis != 'unit':
                raise ValidationError(_("Pegawai harus terdaftar pada unit sekolah, bukan yayasan."))

    @api.depends('work_contact_id', *('work_contact_id.' + f for f in PROFIL_TERKAIT))
    def _compute_nti_edu_profil(self):
        for rec in self:
            kontak = rec.work_contact_id.sudo()
            for f in PROFIL_TERKAIT:
                rec[f] = kontak[f]

    def _inverse_nti_edu_profil(self):
        # Cadangan saja: create/write memisahkan field profil dari vals dan menulis hanya field yang dikirim
        # (nilai cermin lain di cache bisa usang, jadi tidak boleh ikut ditulis).
        for rec in self:
            rec._nti_edu_tulis_profil({f: rec[f] for f in PROFIL_TERKAIT})

    def _nti_edu_tulis_profil(self, nilai):
        """Tulis profil per orang ke kontak kerja: hanya field yang benar-benar berubah; penjaga profil dicek dengan
        hak pemanggil lebih dulu, baru ditulis dengan sudo (pemanggil tidak perlu hak tulis kontak)."""
        self.ensure_one()
        kontak = self.work_contact_id.sudo()
        ubah = {f: v for f, v in nilai.items() if (kontak[f] or False) != (v or False)}
        if not ubah:
            return
        if not kontak:
            raise UserError(_("Pegawai ini belum punya kontak kerja untuk menyimpan profil."))
        if not self.env.su and not self.env['res.partner'].browse(kontak.id)._nti_edu_boleh_ubah_profil_pegawai():
            self.env['res.partner']._nti_edu_tolak_profil()
        kontak.write(ubah)
        # Cermin non-stored di semua penempatan orang ini dibaca ulang dari kontak.
        self.env['hr.employee'].invalidate_model(list(PROFIL_TERKAIT))

    def _inverse_work_contact_details(self):
        """Email/HP kerja milik hr ditulis ke kontak kerja bersama (juga login dan kanal reset kata sandi akunnya).
        hr menulisnya dengan sudo bila pegawai tanpa akun (tanpa cek unit), atau dengan hak pemanggil bila berakun
        (TU tidak punya hak tulis kontak). Untuk grup pegawai: penjaga dicek dengan hak pemanggil, lalu sudo."""
        if self.env.su or not self.env.user.has_group(GRUP_OPERATOR):
            return super()._inverse_work_contact_details()
        tanpa_kontak = self.browse()
        for rec in self:
            kontak = rec.work_contact_id.sudo()
            if not kontak:
                tanpa_kontak |= rec
                continue
            ubah = {}
            if (kontak.email or False) != (rec.work_email or False):
                ubah['email'] = rec.work_email
            if (kontak.mobile or False) != (rec.mobile_phone or False):
                ubah['mobile'] = rec.mobile_phone
            if not ubah:
                continue
            rec._nti_edu_cek_ubah_kontak_kerja(kontak)
            kontak.write(ubah)
        if tanpa_kontak:
            # Pegawai baru tanpa kontak: hr membuat kontaknya dengan sudo (tidak menyentuh data orang lain).
            super(HrEmployee, tanpa_kontak)._inverse_work_contact_details()

    def _nti_edu_cek_ubah_kontak_kerja(self, kontak):
        """Penjaga ubah email/HP kontak kerja (dicek dengan hak pemanggil): penjaga profil lintas unit, kunci kontak
        wali milik base, dan wewenang atas akun login yang memakai kontak itu."""
        partner = self.env['res.partner'].browse(kontak.id)
        if not partner._nti_edu_boleh_ubah_profil_pegawai():
            partner._nti_edu_tolak_profil()
        if kontak.nti_edu_is_wali and not partner._nti_edu_boleh_ubah_kontak_wali():
            raise AccessError(_(
                "Kontak wali hanya boleh diubah oleh walinya sendiri "
                "atau Operator Data Sekolah yang memegang semua unit anaknya."))
        for akun in kontak.with_context(active_test=False).user_ids:
            if akun.id != self.env.uid and not self._nti_edu_wewenang_akun(akun):
                raise AccessError(_("Email/HP kerja pemilik akun ini hanya boleh diubah oleh HRD."))

    # --- Penjaga: akun login, tautan kontak, dan hapus ---

    def _nti_edu_perlu_hrd(self):
        return not self.env.su and not self.env.user.has_group(GRUP_HRD)

    def _nti_edu_cek_tautan_kontak(self, vals):
        """Penjaga kontak kerja yang ditautkan lewat `vals` (create/write), dicek dengan hak pemanggil:
        - selain HRD: `user_id` tidak boleh diisi; kontak harus sudah menjadi kontak kerja pegawai dan semua
          pegawainya (termasuk arsip) berada di unit pemanggil (penempatan lintas unit lewat wizard);
        - semua kecuali superuser: kontak siswa tidak pernah jadi kontak kerja, dan kontak yang dipakai akun login
          hanya boleh ditautkan bersama akun itu sendiri (`user_id` record ini)."""
        if self.env.su:
            return
        perlu_hrd = self._nti_edu_perlu_hrd()
        # Saat buat (self kosong) form mengirim user_id=False; saat ubah, mengosongkan akun pun hanya HRD.
        if perlu_hrd and (vals.get('user_id') if not self else 'user_id' in vals):
            raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        kontak_id = vals.get('work_contact_id')
        if vals.get('user_id'):
            # hr mengganti kontak kerja dengan partner akun yang ditautkan (_sync_user).
            kontak_id = Users.browse(vals['user_id']).partner_id.id
        if not kontak_id:
            return
        kontak = self.env['res.partner'].sudo().with_context(active_test=False).browse(kontak_id)
        if perlu_hrd:
            pemilik = self.env['hr.employee'].sudo().with_context(active_test=False).search(
                [('work_contact_id', '=', kontak.id)])
            if not pemilik or not pemilik.company_id <= self.env.user.company_ids:
                raise AccessError(_(
                    "Kontak kerja hanya boleh diganti ke kontak pegawai di unit yang Anda pegang. "
                    "Gunakan Tempatkan di Unit Lain atau minta HRD."))
        if kontak.nti_edu_is_siswa:
            raise ValidationError(_("Kontak siswa tidak boleh dipakai sebagai kontak kerja pegawai."))
        akun = kontak.user_ids
        if akun:
            if 'user_id' in vals:
                daftar = [Users.browse(vals['user_id'] or [])]
            else:
                daftar = [rec.user_id for rec in self.sudo()] or [Users]
            if any(akun - boleh for boleh in daftar):
                raise ValidationError(_(
                    "Kontak ini dipakai akun login lain; tautkan akun itu sendiri sebagai akun pegawai."))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            self._nti_edu_cek_tautan_kontak(vals)
        # Profil dan sertifikasi disimpan di kontak kerja, yang baru dibuat hr setelah record tersimpan:
        # dipisahkan dari vals lalu diterapkan sesudahnya lewat jalur berpenjaga yang sama.
        profil = [{f: vals.pop(f) for f in PROFIL_TERKAIT if f in vals} for vals in vals_list]
        perintah = [vals.pop('nti_edu_sertifikasi_ids', None) for vals in vals_list]
        pegawai = super().create(vals_list)
        for rec, nilai, cmds in zip(pegawai, profil, perintah):
            if nilai:
                rec._nti_edu_tulis_profil(nilai)
            rec._nti_edu_terapkan_sertifikasi(cmds)
        return pegawai

    def write(self, vals):
        if 'work_contact_id' in vals or 'user_id' in vals:
            self._nti_edu_cek_tautan_kontak(vals)
        vals = dict(vals)
        # Profil dan sertifikasi ditulis sesudah super: bila kontak ikut diganti, masuk ke kontak yang baru;
        # profil hanya field yang dikirim pemanggil (lihat _inverse_nti_edu_profil).
        profil = {f: vals.pop(f) for f in PROFIL_TERKAIT if f in vals}
        cmds = vals.pop('nti_edu_sertifikasi_ids', None)
        hasil = super().write(vals) if vals else True
        if profil:
            for rec in self:
                rec._nti_edu_tulis_profil(profil)
        self._nti_edu_terapkan_sertifikasi(cmds)
        # Wizard penempatan (sudo) mengatur akses akun sendiri dengan hak pemanggilnya.
        if 'active' in vals and not (self.env.su and self.env.context.get('nti_edu_tanpa_sinkron_akun')):
            if vals['active']:
                self._nti_edu_kembalikan_akses_akun()
            else:
                self._nti_edu_sinkron_akses_akun()
        return hasil

    # --- Akses akun login (satu aturan wewenang untuk semua jalur) ---

    @api.model
    def _nti_edu_akun_kebal(self, user):
        """Akun administrator: aksesnya tidak pernah diubah dari data pegawai."""
        user = user.sudo()
        kebal = (self.env.ref('base.group_system') | self.env.ref('base.group_erp_manager')
                 | self.env.ref('nti_edu_base.group_base_admin'))
        admin_ids = {self.env.ref('base.user_root').id, self.env.ref('base.user_admin').id}
        return user.id in admin_ids or bool(user.groups_id & kebal)

    @api.model
    def _nti_edu_wewenang_akun(self, user):
        """Aturan wewenang tunggal atas akun login pegawai (pemanggil = self.env): akun administrator tidak pernah;
        superuser selalu; akun HRD hanya oleh HRD; akun lain boleh (batas unit dicek per unit)."""
        if self._nti_edu_akun_kebal(user):
            return False
        if self.env.su:
            return True
        if user.sudo().has_group(GRUP_HRD):
            return self.env.user.has_group(GRUP_HRD)
        return True

    @api.model
    def _nti_edu_unit_dipegang(self, units):
        """Bagian `units` yang boleh diatur pemanggil pada akun: superuser/HRD semua, TU hanya unit yang ia pegang."""
        if self.env.su or self.env.user.has_group(GRUP_HRD):
            return units
        return units & self.env.user.company_ids.sudo()

    @api.model
    def _nti_edu_atur_akses_akun(self, user, tambah=None, cabut=None, nonaktifkan=False, aktifkan=False,
                                 utama=None, wajib=False):
        """Satu-satunya jalur pengubah akses akun login pegawai: arsip (cabut unit, nonaktifkan), aktif lagi
        (tambah unit), penempatan (tambah unit), dan Aktifkan Akun Login HRD (aktifkan, atur unit).
        Wewenang dicek dengan hak pemanggil (self.env) lebih dulu, lalu akun ditulis dengan sudo:
        - `_nti_edu_wewenang_akun` (administrator tidak disentuh; akun HRD hanya oleh HRD/superuser);
        - unit ditambah/dicabut hanya unit sekolah yang dipegang pemanggil (HRD/superuser: semua);
          perusahaan terakhir akun tidak pernah dicabut;
        - nonaktifkan hanya bila pemanggil HRD/superuser atau memegang semua unit tersisa akun itu, dan bukan
          akun pemanggil sendiri; unit dicabut dulu, baru akun dinonaktifkan;
        - aktifkan hanya dipakai jalur HRD (dicek pemanggilnya); company_id dipindah ke `utama`.
        Tanpa wewenang: diam (jalur otomatis) atau AccessError bila `wajib`. Kembalikan True bila diterapkan."""
        Company = self.env['res.company'].sudo()
        user = user.sudo()
        if not self._nti_edu_wewenang_akun(user):
            if wajib:
                raise AccessError(_("Anda tidak berwenang mengubah akses akun login ini."))
            return False

        def unit_sekolah(companies):
            return companies.filtered(lambda c: c.nti_edu_jenis == 'unit')

        tambah = self._nti_edu_unit_dipegang(unit_sekolah((tambah or Company).sudo()) - user.company_ids)
        cabut = self._nti_edu_unit_dipegang(unit_sekolah((cabut or Company).sudo()) & user.company_ids)
        if nonaktifkan:
            tersisa = unit_sekolah(user.company_ids - cabut)
            nonaktifkan = (self.env.su or self.env.user.has_group(GRUP_HRD)
                           or tersisa <= self.env.user.company_ids.sudo())
            if nonaktifkan and user.id == self.env.uid:
                raise UserError(_("Anda tidak dapat mengarsipkan data pegawai terakhir milik akun Anda sendiri."))
        pool = (user.company_ids | tambah) - cabut
        if not pool:
            # Akun wajib punya satu perusahaan: perusahaan terakhir dipertahankan.
            cabut = Company
            pool = user.company_ids | tambah
        nilai = {}
        if tambah or cabut:
            nilai['company_ids'] = [(4, c.id) for c in tambah] + [(3, c.id) for c in cabut]
        utama = (utama or Company).sudo() & pool
        if user.company_id not in pool or (aktifkan and utama and user.company_id not in utama):
            nilai['company_id'] = (utama or unit_sekolah(pool) or pool)[0].id
        if nonaktifkan:
            nilai['active'] = False
        elif aktifkan:
            nilai['active'] = True
        if nilai:
            user.write(nilai)
        return True

    def _nti_edu_pegawai_aktif_akun(self, user):
        """Pegawai aktif milik akun: ditautkan lewat user_id atau lewat kontak kerja = partner akun."""
        return self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            '|', ('user_id', '=', user.id), ('work_contact_id', '=', user.partner_id.id)])

    def _nti_edu_sinkron_akses_akun(self):
        """Setelah pegawai diarsipkan: cabut unit record yang diarsipkan dari akunnya bila akun itu tak punya pegawai
        aktif lain di unit tsb; tanpa pegawai aktif tersisa, akun juga dinonaktifkan (sesuai wewenang).
        Tidak pernah mengaktifkan ulang akun."""
        for user in self.sudo().user_id:
            if not user.active:
                continue
            diarsip = self.sudo().filtered(lambda e: e.user_id == user)
            sisa = self._nti_edu_pegawai_aktif_akun(user)
            self._nti_edu_atur_akses_akun(
                user, cabut=diarsip.company_id - sisa.company_id, nonaktifkan=not sisa, utama=sisa.company_id)

    def _nti_edu_kembalikan_akses_akun(self):
        """Setelah pegawai diaktifkan lagi: unitnya dikembalikan ke akun yang masih aktif (sesuai wewenang).
        Akun nonaktif tidak diaktifkan di sini (tombol Aktifkan Akun Login, HRD)."""
        for user in self.sudo().user_id:
            if user.active:
                aktif = self.sudo().filtered(lambda e: e.user_id == user and e.active)
                self._nti_edu_atur_akses_akun(user, tambah=aktif.company_id)

    def action_nti_edu_aktifkan_akun_login(self):
        """HRD: aktifkan kembali akun login pegawai yang nonaktif; unitnya = unit semua pegawai aktif orang itu
        (perusahaan non-unit yang sudah ada dipertahankan)."""
        self.ensure_one()
        if self._nti_edu_perlu_hrd():
            raise AccessError(_("Akun login pegawai hanya boleh diaktifkan kembali oleh HRD."))
        user = self.sudo().user_id
        if not user:
            raise UserError(_("Pegawai ini belum punya akun login."))
        if user.active:
            return True
        unit = self._nti_edu_pegawai_aktif_akun(user).company_id.filtered(lambda c: c.nti_edu_jenis == 'unit')
        if not unit:
            raise UserError(_("Akun ini tidak punya data pegawai aktif; aktifkan data pegawainya lebih dulu."))
        cabut = user.company_ids.filtered(lambda c: c.nti_edu_jenis == 'unit') - unit
        self._nti_edu_atur_akses_akun(user, tambah=unit, cabut=cabut, aktifkan=True, utama=unit, wajib=True)
        return True

    def _nti_edu_terapkan_sertifikasi(self, cmds):
        """Terapkan perintah One2many sertifikasi lewat model sertifikasi dengan hak pemanggil (bukan sudo),
        sehingga penjaga profil lintas unit dan penjaga hapus tetap berlaku; hak tulis kontak tidak dipakai."""
        if not cmds:
            return
        Sert = self.env['nti_edu.pegawai.sertifikasi']
        for rec in self:
            kontak = rec.work_contact_id
            if not kontak:
                raise AccessError(_("Pegawai belum punya kontak kerja untuk menyimpan sertifikasi."))
            milik = Sert.sudo().search([('partner_id', '=', kontak.id)]).ids
            for cmd in cmds:
                aksi = cmd[0]
                if aksi == 0:
                    Sert.create(dict(cmd[2], partner_id=kontak.id))
                elif aksi in (1, 2, 3, 4):
                    if cmd[1] not in milik:
                        raise AccessError(_("Sertifikasi ini bukan milik pegawai tersebut."))
                    if aksi == 1:
                        Sert.browse(cmd[1]).write(cmd[2])
                    elif aksi in (2, 3):
                        Sert.browse(cmd[1]).unlink()
                elif aksi == 5:
                    Sert.browse(milik).unlink()
                elif aksi == 6:
                    Sert.browse(set(milik) - set(cmd[2])).unlink()

    def unlink(self):
        if self._nti_edu_perlu_hrd():
            raise AccessError(_("Pegawai hanya boleh dihapus oleh HRD. Arsipkan pegawai ini bila sudah tidak aktif."))
        return super().unlink()

    def action_nti_edu_buat_akun_login(self):
        """Buka wizard Buat Akun Login untuk pegawai ini."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Buat Akun Login"),
            'res_model': 'nti_edu.pegawai.akun.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

    def action_nti_edu_tempatkan(self):
        """Buka wizard Tempatkan di Unit Lain untuk pegawai ini."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Tempatkan di Unit Lain"),
            'res_model': 'nti_edu.pegawai.penempatan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }
