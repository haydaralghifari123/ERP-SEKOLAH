# -*- coding: utf-8 -*-
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

GRUP_OPERATOR = 'nti_edu_base.group_base_operator'


class AkunPortalWizard(models.TransientModel):
    _name = 'nti_edu.akun.portal.wizard'
    _description = 'Wizard Akun Portal Siswa/Wali'
    # Baris memuat kata sandi awal: dibersihkan secepatnya (seperti change.password.wizard).
    _transient_max_hours = 0.1

    partner_id = fields.Many2one('res.partner', string='Siswa/Wali', required=True)
    # compute_sudo=False: nilai bawaan hanya dihitung bila pemanggil berhak atas partner (hindari bocor NISN/NIS).
    login = fields.Char(
        string='Login', compute='_compute_login', store=True, readonly=False, compute_sudo=False)
    password_awal = fields.Char(string='Kata Sandi Awal', readonly=True)
    state = fields.Selection([('isi', 'Isi'), ('selesai', 'Selesai')], string='Status', default='isi')

    @api.depends('partner_id')
    def _compute_login(self):
        for rec in self:
            try:
                if rec.partner_id and rec.partner_id.has_access('write'):
                    rec.login = rec.partner_id._nti_edu_login_default()
                else:
                    rec.login = False
            except UserError:
                # Pesan jelasnya muncul saat tombol dijalankan; di form login boleh diisi manual.
                rec.login = False

    def action_tutup(self):
        """Tutup dialog dan hapus kata sandi awal supaya tidak tersisa di baris sementara."""
        self.ensure_one()
        self.password_awal = False
        return {'type': 'ir.actions.act_window_close'}

    def action_buat(self):
        self.ensure_one()
        if not self.env.user.has_group(GRUP_OPERATOR):
            raise AccessError(_("Hanya Operator Data Sekolah yang boleh membuat akun portal."))
        partner = self.partner_id
        # Many2one tidak dicek aksesnya saat wizard dibuat: pastikan pemanggil berhak menulis partner ini.
        partner.with_env(self.env).check_access('write')

        Users = self.env['res.users'].sudo().with_context(active_test=False)
        pengguna = Users.search([('partner_id', '=', partner.id)])
        if pengguna.filtered(lambda u: not u.share):
            raise UserError(_(
                "%s sudah punya akun internal; menu Anak Saya bisa dibuka dari akun itu.", partner.display_name))
        if pengguna:
            raise UserError(_("%s sudah punya akun portal.", partner.display_name))

        partner_sudo = partner.sudo()
        if not partner_sudo.active:
            raise UserError(_("%s sudah diarsipkan; akun portal tidak bisa dibuat.", partner.display_name))
        if not (partner_sudo.nti_edu_is_siswa or partner_sudo.nti_edu_is_wali):
            raise UserError(_("%s bukan siswa atau wali siswa.", partner.display_name))
        if partner_sudo.nti_edu_is_siswa:
            if partner_sudo.nti_edu_status != 'aktif':
                raise UserError(_("Siswa %s tidak berstatus aktif; akun portal tidak bisa dibuat.", partner.display_name))
            unit_anak = partner_sudo.company_id
        else:
            unit_anak = partner_sudo.nti_edu_anak_ids.siswa_id.company_id
            if not unit_anak <= self.env.user.company_ids:
                raise AccessError(_(
                    "Wali %s punya anak di unit yang tidak Anda pegang; akun portal hanya bisa dibuat "
                    "oleh operator yang memegang semua unit anaknya.", partner.display_name))

        login = (self.login or '').strip() or partner._nti_edu_login_default()
        if Users.search_count([('login', '=', login)]):
            raise UserError(_("Login %s sudah dipakai pengguna lain; ubah login lalu coba lagi.", login))

        # Siswa: unitnya saja. Wali: semua unit anaknya; unit aktif operator dipilih bila termasuk.
        perusahaan = unit_anak
        utama = self.env.company if self.env.company in perusahaan else perusahaan[:1]
        user = Users.with_context(no_reset_password=True).create({
            'name': partner.name,
            'login': login,
            'partner_id': partner.id,
            'company_id': utama.id,
            'company_ids': [(6, 0, perusahaan.ids)],
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        password_awal = False
        if partner.sudo().email:
            user.action_reset_password()
        else:
            password_awal = secrets.token_urlsafe(8)
            user.password = password_awal
        self.write({'login': login, 'password_awal': password_awal, 'state': 'selesai'})
        return {
            'type': 'ir.actions.act_window',
            'name': _("Akun Portal"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
