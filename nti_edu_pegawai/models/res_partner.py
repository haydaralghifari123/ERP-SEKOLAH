# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

GRUP_OPERATOR = 'nti_edu_pegawai.group_pegawai_operator'
GRUP_HRD = 'nti_edu_pegawai.group_pegawai_hrd'

# Profil per orang (bukan per penempatan); dijaga lintas unit (lihat write).
FIELD_PROFIL = {
    'nti_edu_nuptk', 'nti_edu_nip', 'nti_edu_status_kepegawaian', 'nti_edu_pendidikan_terakhir',
    'nti_edu_bidang_studi', 'nti_edu_sertifikasi_ids',
}
# Nomor identitas dirapikan (spasi tepi dibuang) agar keunikan tidak lolos karena spasi.
FIELD_NOMOR = ('nti_edu_nuptk', 'nti_edu_nip')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nti_edu_nuptk = fields.Char(string='NUPTK', copy=False, groups=GRUP_OPERATOR)
    nti_edu_nip = fields.Char(string='NIP', copy=False, groups=GRUP_OPERATOR)
    nti_edu_status_kepegawaian = fields.Selection([
        ('pns', 'PNS'), ('pppk', 'PPPK'), ('gty', 'GTY/PTY'), ('gtt', 'GTT/PTT'),
        ('honorer', 'Honorer'), ('lainnya', 'Lainnya'),
    ], string='Status Kepegawaian', groups=GRUP_OPERATOR)
    nti_edu_pendidikan_terakhir = fields.Selection([
        ('sma', 'SMA/Sederajat'), ('d1', 'D1'), ('d2', 'D2'), ('d3', 'D3'), ('d4', 'D4'),
        ('s1', 'S1'), ('s2', 'S2'), ('s3', 'S3'),
    ], string='Pendidikan Terakhir', groups=GRUP_OPERATOR)
    nti_edu_bidang_studi = fields.Char(string='Bidang Studi', groups=GRUP_OPERATOR)
    nti_edu_sertifikasi_ids = fields.One2many(
        'nti_edu.pegawai.sertifikasi', 'partner_id', string='Sertifikasi', groups=GRUP_OPERATOR)
    nti_edu_is_pegawai = fields.Boolean(
        string='Pegawai', compute='_compute_nti_edu_is_pegawai', store=True, index=True)

    @api.depends('employee_ids.active')
    def _compute_nti_edu_is_pegawai(self):
        for rec in self:
            pegawai = rec.sudo().with_context(active_test=False).employee_ids
            rec.nti_edu_is_pegawai = any(pegawai.mapped('active'))

    def _nti_edu_cek_unik(self, field, label):
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        for rec in self.sudo().filtered(field):
            if Partner.search_count([('id', '!=', rec.id), (field, '=', rec[field])]):
                # Sengaja tidak menyebut pemilik/unit nomor yang sama.
                raise ValidationError(_("%(label)s %(nilai)s sudah terdaftar.", label=label, nilai=rec[field]))

    @api.constrains('nti_edu_nuptk')
    def _check_nti_edu_nuptk_unik(self):
        self._nti_edu_cek_unik('nti_edu_nuptk', 'NUPTK')

    @api.constrains('nti_edu_nip')
    def _check_nti_edu_nip_unik(self):
        self._nti_edu_cek_unik('nti_edu_nip', 'NIP')

    # --- Penjaga tulis: profil per orang lintas unit ---

    def _nti_edu_boleh_ubah_profil_pegawai(self):
        """Apakah user saat ini boleh mengubah profil kepegawaian kontak ini (self = satu kontak)."""
        self.ensure_one()
        if self.env.su:
            return True
        user = self.env.user
        if user.has_group(GRUP_HRD):
            return True
        if not user.has_group(GRUP_OPERATOR):
            return False
        # Semua unit tempat orang ini bekerja harus termasuk unit TU; kontak tanpa pegawai aktif hanya HRD.
        # Sengaja user.company_ids (semua unit yang dipegang), bukan unit aktif di pemilih perusahaan: ini soal hak
        # atas orangnya, tidak boleh berubah karena pilihan tampilan. Aturan baca sertifikasi (ir.rule) memakai
        # `company_ids` (unit aktif di pemilih) seperti aturan multi-company standar, sehingga yang terbaca
        # mengikuti unit yang sedang dipilih sedangkan hak ubah tetap dicek terhadap semua unit TU.
        unit_pegawai = self.sudo().employee_ids.company_id
        # Orang dengan penempatan aktif di yayasan (staf yayasan) hanya diubah HRD, walau TU diberi company yayasan.
        if any(c.nti_edu_jenis == 'yayasan' for c in unit_pegawai):
            return False
        return bool(unit_pegawai) and unit_pegawai <= user.company_ids

    def _nti_edu_tolak_profil(self):
        raise AccessError(_(
            "Profil kepegawaian hanya boleh diubah HRD atau TU yang memegang semua unit tempat pegawai ini bekerja "
            "(profil staf yayasan hanya oleh HRD)."))

    @api.model
    def _nti_edu_rapikan_nomor(self, vals):
        for field in FIELD_NOMOR:
            if isinstance(vals.get(field), str):
                vals[field] = vals[field].strip() or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._nti_edu_rapikan_nomor(dict(vals)) for vals in vals_list]
        # Belum ada pegawai pada kontak baru: profil hanya boleh diisi HRD/su.
        if (not self.env.su and not self.env.user.has_group(GRUP_HRD)
                and any(FIELD_PROFIL & set(vals) for vals in vals_list)):
            self._nti_edu_tolak_profil()
        return super().create(vals_list)

    def write(self, vals):
        if self and not self.env.su and FIELD_PROFIL & set(vals):
            for rec in self:
                if not rec._nti_edu_boleh_ubah_profil_pegawai():
                    self._nti_edu_tolak_profil()
        # NIK dipakai bersama siswa/wali; hanya dijaga bila kontak ini pegawai aktif.
        if self and not self.env.su and 'nti_edu_nik' in vals:
            for rec in self.filtered(lambda r: r.sudo().employee_ids):
                if not rec._nti_edu_boleh_ubah_profil_pegawai():
                    self._nti_edu_tolak_profil()
        return super().write(self._nti_edu_rapikan_nomor(dict(vals)))
