# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

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
        Partner = self.env['res.partner']
        for rec in self:
            if not rec.work_contact_id:
                continue
            if not Partner.browse(rec.work_contact_id.id)._nti_edu_boleh_ubah_profil_pegawai():
                Partner._nti_edu_tolak_profil()
            rec.work_contact_id.sudo().write({f: rec[f] for f in PROFIL_TERKAIT})

    # --- Penjaga: akun login dan hapus hanya HRD ---

    def _nti_edu_perlu_hrd(self):
        return not self.env.su and not self.env.user.has_group(GRUP_HRD)

    def _nti_edu_cek_tautan_kontak(self, kontak_id):
        """Kontak yang sudah jadi pegawai di unit lain tidak boleh ditautkan oleh TU yang tak memegang unit itu."""
        if not kontak_id:
            return
        pegawai = self.env['hr.employee'].sudo().search([
            ('work_contact_id', '=', kontak_id), ('id', 'not in', self.ids)])
        if not pegawai.company_id <= self.env.user.company_ids:
            raise AccessError(_("Menempatkan pegawai dari unit lain hanya boleh oleh HRD atau TU yang memegang kedua unit."))

    @api.model_create_multi
    def create(self, vals_list):
        if self._nti_edu_perlu_hrd():
            if any(vals.get('user_id') for vals in vals_list):
                raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
            for vals in vals_list:
                self._nti_edu_cek_tautan_kontak(vals.get('work_contact_id'))
        vals_list = [dict(vals) for vals in vals_list]
        perintah = [vals.pop('nti_edu_sertifikasi_ids', None) for vals in vals_list]
        pegawai = super().create(vals_list)
        for rec, cmds in zip(pegawai, perintah):
            rec._nti_edu_terapkan_sertifikasi(cmds)
        return pegawai

    def write(self, vals):
        if self._nti_edu_perlu_hrd():
            if 'user_id' in vals:
                raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
            self._nti_edu_cek_tautan_kontak(vals.get('work_contact_id'))
        if 'nti_edu_sertifikasi_ids' in vals:
            vals = dict(vals)
            cmds = vals.pop('nti_edu_sertifikasi_ids')
            self._nti_edu_terapkan_sertifikasi(cmds)
        return super().write(vals) if vals else True

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
