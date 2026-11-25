/** Uji asap layar Data Sekolah: membuka setiap menu, view, dan form agar galat sisi klien (Owl) ketahuan. */
import { registry } from "@web/core/registry";

const APP = "nti_edu_base.menu_data_sekolah";
const REMAH = ".o_control_panel .o_last_breadcrumb_item.active";
const KARTU = ".o_kanban_view .o_kanban_record:not(.o_kanban_ghost)";
const BARIS = ".o_list_view .o_data_row";

// Tunggu layar baru lewat judul remah roti (unik per layar), baru periksa isinya,
// supaya langkah tidak lulus karena layar sebelumnya masih terpasang.
const judul = (nama) => ({ content: `Layar ${nama} tampil`, trigger: `${REMAH}:contains('${nama}')` });

function langkahMenu({ xmlid, nama, induk, views = [], form = false, kosong = false }) {
    const langkah = [];
    if (induk) {
        langkah.push(
            {
                content: `Buka menu induk ${induk}`,
                trigger: `.o_menu_sections button[data-menu-xmlid="nti_edu_base.${induk}"]`,
                run: "click",
            },
            {
                content: `Pilih menu ${xmlid}`,
                trigger: `.dropdown-menu [data-menu-xmlid="nti_edu_base.${xmlid}"]`,
                run: "click",
            }
        );
    } else {
        langkah.push({
            content: `Pilih menu ${xmlid}`,
            trigger: `.o_menu_sections [data-menu-xmlid="nti_edu_base.${xmlid}"]`,
            run: "click",
        });
    }
    langkah.push(judul(nama));
    for (const view of views) {
        if (view === "kanban") {
            langkah.push(
                { content: "Ganti ke kanban", trigger: ".o_switch_view.o_kanban", run: "click" },
                { content: "Kanban tampil dengan kartu", trigger: KARTU }
            );
        } else {
            langkah.push(
                { content: "Ganti ke list", trigger: ".o_switch_view.o_list", run: "click" },
                { content: "List tampil dengan baris", trigger: BARIS }
            );
        }
    }
    if (!views.length) {
        langkah.push(
            kosong
                ? { content: "List kosong tampil", trigger: ".o_list_view .o_list_table" }
                : { content: "List tampil dengan baris", trigger: BARIS }
        );
    }
    if (form) {
        langkah.push(
            { content: "Buka record pertama", trigger: `${BARIS}:first td.o_data_cell, ${KARTU}:first`, run: "click" },
            { content: "Form tampil", trigger: `.o_form_view .o_form_sheet` },
            { content: "Kembali", trigger: ".o_back_button", run: "click" },
            judul(nama),
            { content: "Daftar tampil lagi", trigger: `${BARIS}, ${KARTU}` }
        );
    }
    return langkah;
}

const tanpaModal = (content) => ({ content, trigger: "body:not(:has(.modal))" });

function langkahWizard() {
    return [
        { content: "Ke list siswa", trigger: ".o_menu_sections [data-menu-xmlid='nti_edu_base.menu_siswa']", run: "click" },
        judul("Siswa"),
        { content: "Ganti ke list", trigger: ".o_switch_view.o_list", run: "click" },
        { content: "Centang satu siswa", trigger: `${BARIS}:first .o_list_record_selector input`, run: "click" },
        {
            content: "Klik Tambah ke Rombel",
            trigger: ".o_control_panel button:contains('Tambah ke Rombel')",
            run: "click",
        },
        { content: "Wizard tampil", trigger: ".modal .o_form_view" },
        { content: "Batal", trigger: ".modal-footer button:contains('Batal')", run: "click" },
        tanpaModal("Wizard tambah tertutup"),
        { content: "Ke menu Rombel", trigger: ".o_menu_sections [data-menu-xmlid='nti_edu_base.menu_rombel']", run: "click" },
        judul("Rombel"),
        { content: "Buka rombel pertama", trigger: `${BARIS}:first td.o_data_cell`, run: "click" },
        { content: "Klik Kenaikan Kelas", trigger: ".o_form_view button:contains('Kenaikan Kelas')", run: "click" },
        { content: "Wizard kenaikan tampil", trigger: ".modal .o_form_view" },
        { content: "Tutup", trigger: ".modal-footer button:contains('Tutup')", run: "click" },
        tanpaModal("Wizard kenaikan tertutup"),
        { content: "Form rombel kembali", trigger: ".o_form_view .o_form_sheet" },
    ];
}

const menuUmum = () => [
    ...langkahMenu({ xmlid: "menu_siswa", nama: "Siswa", views: ["list", "kanban"], form: true }),
    ...langkahMenu({ xmlid: "menu_rombel", nama: "Rombel", form: true }),
    ...langkahMenu({ xmlid: "menu_tahun_ajaran", nama: "Tahun Ajaran", induk: "menu_kalender", form: true }),
    ...langkahMenu({ xmlid: "menu_hari_libur", nama: "Hari Libur", induk: "menu_kalender" }),
    ...langkahMenu({ xmlid: "menu_wali", nama: "Wali Murid", form: true }),
];

const mulai = () => [
    { content: "Buka menu aplikasi", trigger: ".o_navbar_apps_menu button:enabled", run: "click" },
    { content: "Buka aplikasi Data Sekolah", trigger: `.o_app[data-menu-xmlid="${APP}"]`, run: "click" },
];

registry.category("web_tour.tours").add("nti_edu_base_asap", {
    steps: () => [
        ...mulai(),
        ...menuUmum(),
        ...langkahMenu({ xmlid: "menu_unit", nama: "Unit Sekolah", induk: "menu_konfigurasi", form: true }),
        ...langkahMenu({ xmlid: "menu_jenjang", nama: "Jenjang", induk: "menu_konfigurasi", form: true }),
        ...langkahMenu({ xmlid: "menu_jurusan", nama: "Jurusan", induk: "menu_konfigurasi", kosong: true }),
        ...langkahMenu({ xmlid: "menu_mapel", nama: "Mata Pelajaran", induk: "menu_konfigurasi", kosong: true }),
        ...langkahMenu({ xmlid: "menu_ruang", nama: "Ruang", induk: "menu_konfigurasi", kosong: true }),
        ...langkahWizard(),
    ],
});

registry.category("web_tour.tours").add("nti_edu_base_asap_operator", {
    steps: () => [...mulai(), ...menuUmum(), ...langkahWizard()],
});
