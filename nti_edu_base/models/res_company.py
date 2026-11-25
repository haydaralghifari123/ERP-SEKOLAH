# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# Field standar res.company yang boleh diubah Admin Data Sekolah (selain semua field nti_edu_*).
FIELD_BOLEH_ADMIN_DATA = {
    'name', 'logo', 'street', 'street2', 'city', 'zip', 'state_id', 'phone', 'email', 'website',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    nti_edu_jenis = fields.Selection(
        [('yayasan', 'Yayasan'), ('unit', 'Unit Sekolah')],
        string='Jenis Entitas', default='unit', required=True)
    nti_edu_jenjang_id = fields.Many2one('nti_edu.jenjang', string='Jenjang')
    nti_edu_npsn = fields.Char(string='NPSN')
    nti_edu_kode = fields.Char(string='Kode Unit')
    nti_edu_kepala_id = fields.Many2one('res.users', string='Kepala Sekolah')
    nti_edu_hari_sekolah = fields.Selection(
        [('5', '5 hari'), ('6', '6 hari')], string='Hari Sekolah', default='5')

    @api.model
    def _nti_edu_tahun_ajaran_aktif(self):
        """Tahun ajaran yang sedang aktif (recordset kosong bila belum ada)."""
        return self.env['nti_edu.tahun.ajaran']._get_aktif()

    @api.model
    def _nti_edu_semester_aktif(self):
        """Semester aktif pada tahun ajaran aktif (recordset kosong bila tidak ada)."""
        return self.env['nti_edu.semester']._get_aktif()

    def _nti_edu_hari_efektif(self, tanggal, company=None):
        """True bila `tanggal` adalah hari efektif sekolah untuk satu unit.

        Unit yang dipakai: `company` bila diberikan, selain itu `self` bila tidak kosong, selain itu
        company aktif (`self.env.company`).
        Bukan hari efektif: Minggu, Sabtu pada unit 5 hari, atau tanggal yang tercakup hari libur
        (global, milik unit ini, atau milik yayasan induknya)."""
        unit = company or self or self.env.company
        unit.ensure_one()
        hari = tanggal.weekday()
        if hari == 6 or (hari == 5 and unit.nti_edu_hari_sekolah == '5'):
            return False
        # sudo: libur tingkat yayasan harus terlihat oleh semua unit, apa pun record rule pemanggil.
        libur = self.env['nti_edu.hari.libur'].sudo().search_count([
            ('company_id', 'in', [False, unit.id, unit.parent_id.id]),
            ('tanggal_mulai', '<=', tanggal),
            '|', '&', ('tanggal_selesai', '=', False), ('tanggal_mulai', '=', tanggal),
            ('tanggal_selesai', '>=', tanggal),
        ])
        return not libur

    @api.constrains('nti_edu_kode')
    def _cek_kode_unik(self):
        # sudo + active_test=False: unit yang tidak terlihat atau diarsipkan tetap memakai kodenya.
        Company = self.env['res.company'].sudo().with_context(active_test=False)
        for rec in self.filtered('nti_edu_kode'):
            if Company.search_count([('nti_edu_kode', '=', rec.nti_edu_kode), ('id', '!=', rec.id)]):
                raise ValidationError(_('Kode unit "%s" sudah dipakai unit lain.', rec.nti_edu_kode))

    @api.constrains('nti_edu_jenis')
    def _cek_jenis_unit_berisi_data(self):
        for rec in self.filtered(lambda c: c.nti_edu_jenis != 'unit'):
            domain = [('company_id', '=', rec.id)]
            if (self.env['nti_edu.rombel'].sudo().with_context(active_test=False).search_count(domain)
                    or self.env['nti_edu.ruang'].sudo().with_context(active_test=False).search_count(domain)):
                raise ValidationError(_(
                    'Jenis "%s" tidak bisa diubah menjadi bukan unit karena masih memiliki rombel atau ruang.',
                    rec.name))

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group('base.group_erp_manager'):
            terlarang = sorted(f for f in vals if not (f.startswith('nti_edu_') or f in FIELD_BOLEH_ADMIN_DATA))
            if terlarang:
                raise AccessError(_(
                    'Admin Data Sekolah hanya boleh mengubah data identitas dan pengaturan sekolah; '
                    'field berikut tidak diizinkan: %s.', ', '.join(terlarang)))
            if self - self.env.user.company_ids:
                raise AccessError(_('Anda hanya boleh mengubah unit sekolah yang menjadi akses Anda.'))
        return super().write(vals)
