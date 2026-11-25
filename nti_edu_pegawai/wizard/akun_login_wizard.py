# -*- coding: utf-8 -*-
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.res_partner import GRUP_OPERATOR


class AkunLoginWizard(models.TransientModel):
    _name = 'nti_edu.pegawai.akun.wizard'
    _description = 'Wizard Akun Login Pegawai'
    # Baris memuat kata sandi awal: dibersihkan secepatnya (seperti change.password.wizard).
    _transient_max_hours = 0.1

    employee_id = fields.Many2one('hr.employee', string='Pegawai', required=True)
    # compute_sudo=False: nilai bawaan hanya dihitung bila pemanggil berhak atas kontak pegawai.
    login = fields.Char(
        string='Login', compute='_compute_login', store=True, readonly=False, compute_sudo=False)
    password_awal = fields.Char(string='Kata Sandi Awal', readonly=True)
    state = fields.Selection([('isi', 'Isi'), ('selesai', 'Selesai')], string='Status', default='isi')

    @api.depends('employee_id')
    def _compute_login(self):
        for rec in self:
            kontak = rec.employee_id.work_contact_id
            if kontak and kontak._nti_edu_boleh_ubah_profil_pegawai():
                rec.login = (kontak.sudo().email or '').strip() or False
            else:
                rec.login = False

    def action_tutup(self):
        """Tutup dialog dan hapus kata sandi awal supaya tidak tersisa di baris sementara."""
        self.ensure_one()
        self.password_awal = False
        return {'type': 'ir.actions.act_window_close'}

    def action_buat(self):
        self.ensure_one()
        if not self.env.user.has_group(GRUP_OPERATOR):
            raise AccessError(_("Hanya TU Pegawai yang boleh membuat akun login pegawai."))
        pegawai = self.employee_id
        kontak = pegawai.work_contact_id
        if not kontak:
            raise UserError(_("Pegawai ini belum punya kontak kerja."))
        # Penjaga dicek dengan hak pemanggil sebelum sudo apa pun.
        if not kontak._nti_edu_boleh_ubah_profil_pegawai():
            raise AccessError(_(
                "Akun login hanya boleh dibuat HRD atau TU yang memegang semua unit tempat pegawai ini bekerja."))

        Users = self.env['res.users'].sudo().with_context(active_test=False)
        semua = self.env['hr.employee'].sudo().search([('work_contact_id', '=', kontak.id)])
        nama = pegawai.sudo().name
        if semua.user_id or kontak.sudo().with_context(active_test=False).user_ids:
            raise UserError(_("%s sudah punya akun login.", nama))
        if not pegawai.sudo().active:
            raise UserError(_("%s sudah diarsipkan; akun login tidak bisa dibuat.", nama))
        aktif = semua.filtered('active')

        login = (self.login or '').strip()
        if not login:
            raise UserError(_("Isi login terlebih dahulu (email kerja pegawai kosong)."))
        if Users.search_count([('login', '=', login)]):
            # Sengaja tidak menyebut pemilik login.
            raise UserError(_("Login sudah dipakai; ubah login lalu coba lagi."))

        user = Users.with_context(no_reset_password=True).create({
            'name': kontak.sudo().name,
            'login': login,
            'partner_id': kontak.id,
            'company_id': pegawai.sudo().company_id.id,
            'company_ids': [(6, 0, aktif.company_id.ids)],
            # Hanya grup dasar; hak operator/HRD diberikan terpisah oleh administrator.
            'groups_id': [(6, 0, [self.env.ref('nti_edu_base.group_base_pengguna').id])],
        })
        # hr mengharuskan satu record per penulisan user_id.
        for rec in aktif:
            rec.write({'user_id': user.id})
        password_awal = False
        if kontak.sudo().email:
            user.with_context(create_user=True).action_reset_password()
        else:
            password_awal = secrets.token_urlsafe(8)
            user.password = password_awal
        self.write({'login': login, 'password_awal': password_awal, 'state': 'selesai'})
        return {
            'type': 'ir.actions.act_window',
            'name': _("Akun Login"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
