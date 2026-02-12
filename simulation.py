import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId

# ==========================
# TEMA Y APARIENCIA
# ==========================
THEME = {
    "bg_main": "#f0f2f5",
    "bg_panel": "#ffffff",
    "bg_canvas": "#fafbfc",
    "accent": "#1877f2",
    "accent_hover": "#166fe5",
    "success": "#42b72a",
    "danger": "#e74c3c",
    "info": "#17a2b8",
    "text": "#1c1e21",
    "text_secondary": "#65676b",
    "border": "#dddfe2",
    "font_family": "Segoe UI",
    "font_title": ("Segoe UI", 11, "bold"),
    "font_body": ("Segoe UI", 10),
    "font_small": ("Segoe UI", 9),
    "pad_sm": 6,
    "pad_md": 10,
    "pad_lg": 14,
    "radius_btn": 0,
}

# ==========================
# CONFIGURACIÓN MONGODB
# ==========================

MONGO_URI = "mongodb+srv://franciscosanchez22s_db_user:0515@cluster0.mryzl7w.mongodb.net/?appName=Cluster0"
DB_NAME = "mir_simulador"
COLL_PRODUCTS = "productos"
COLL_RUNS = "recorridos"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
products_coll = db[COLL_PRODUCTS]
runs_coll = db[COLL_RUNS]


# ==========================
# MODELO DE DATOS
# ==========================

class Robot:
    def __init__(self, robot_id: int):
        self.robot_id = robot_id
        self.status = "disponible"  # disponible | en_recorrido
        self.assigned_products = []  # lista de dicts {product_id, name, qty}
        self.destination_label = None  # B, C o D
        self.destination_point = None  # (x, y)


# ==========================
# LÓGICA BASE DE DATOS
# ==========================

def get_all_products():
    """Devuelve todos los productos de la colección."""
    return list(products_coll.find().sort("nombre", 1))


def ensure_sample_products():
    """Precarga algunos productos si la colección está vacía."""
    if products_coll.count_documents({}) == 0:
        sample = [
            {"nombre": "Producto A", "stock": 100},
            {"nombre": "Producto B", "stock": 50},
            {"nombre": "Producto C", "stock": 75},
        ]
        products_coll.insert_many(sample)


def update_stock_for_pick(assigned_products):
    """
    Resta del stock de MongoDB los productos tomados en el punto A.
    assigned_products: [{product_id, name, qty}]
    """
    # Verificación previa de stock
    for item in assigned_products:
        prod = products_coll.find_one({"_id": item["product_id"]})
        if not prod:
            raise ValueError(f"Producto no encontrado: {item['name']}")
        if prod["stock"] < item["qty"]:
            raise ValueError(
                f"Stock insuficiente para {item['name']}. Stock: {prod['stock']}, requerido: {item['qty']}"
            )

    # Aplicar las restas
    for item in assigned_products:
        products_coll.update_one(
            {"_id": item["product_id"]},
            {"$inc": {"stock": -item["qty"]}}
        )


def log_run(robot: Robot, assigned_products):
    """
    Registra un recorrido en la colección runs_coll.
    """
    now = datetime.now()
    doc = {
        "robot_id": robot.robot_id,
        "timestamp": now,
        "from_point": "Origen",
        "pickup_point": "Almacén (Punto A)",
        "dropoff_point": robot.destination_label or "Punto B",
        "finished_at_station": True,
        "productos": [
            {
                "product_id": str(p["product_id"]),
                "nombre": p["name"],
                "cantidad": p["qty"],
            }
            for p in assigned_products
        ],
    }
    runs_coll.insert_one(doc)


# ==========================
# GUI PRINCIPAL
# ==========================

class MiRSimulatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Simulador MiR - Origen → Almacén (A) → B / C / D")
        self.root.configure(bg=THEME["bg_main"])
        self.root.option_add("*Font", THEME["font_body"])

        # Robots en memoria
        self.robots = []
        self.next_robot_id = 1
        self.robot_markers = {}  # robot_id -> canvas item id
        self._current_runs = []  # Lista de recorridos actuales

        # Guardamos snapshot inicial de productos
        ensure_sample_products()
        self.initial_products_snapshot = get_all_products()

        # Layout principal
        self.build_layout()

        # Dibujar entorno de simulación
        self.setup_canvas()

        # Cargar productos en listas
        self.refresh_product_lists()

        # Crear un robot inicial
        self.add_robot()

    # ------------------------------
    # Funciones auxiliares necesarias
    # ------------------------------
    def _reserved_stock(self, product_id):
        """Calcula el stock reservado por robots."""
        total = 0
        for robot in self.robots:
            for item in robot.assigned_products:
                if item["product_id"] == product_id:
                    total += item["qty"]
        return total
    
    def _get_oid(self, oid_str):
        """Convierte string a ObjectId."""
        try:
            return ObjectId(oid_str)
        except:
            return None

    # ------------------------------
    # Construcción de la interfaz
    # ------------------------------
    def build_layout(self):
        pad = THEME["pad_md"]
        main_frame = tk.Frame(self.root, bg=THEME["bg_main"])
        main_frame.pack(fill="both", expand=True, padx=pad, pady=pad)

        # Panel izquierdo: robots
        left_frame = tk.LabelFrame(
            main_frame, text="  Robots  ", bg=THEME["bg_panel"], fg=THEME["text"],
            font=THEME["font_title"], relief="flat", bd=0,
            highlightbackground=THEME["border"], highlightthickness=1
        )
        left_frame.grid(row=0, column=0, sticky="ns", padx=5, pady=5)

        self.robots_listbox = tk.Listbox(
            left_frame, height=8, width=28, bg=THEME["bg_panel"], fg=THEME["text"],
            font=THEME["font_small"], relief="flat", highlightthickness=0,
            selectbackground=THEME["accent"], selectforeground="white"
        )
        self.robots_listbox.pack(side="top", fill="x", padx=THEME["pad_sm"], pady=THEME["pad_sm"])
        self.robots_listbox.bind("<<ListboxSelect>>", self.on_robot_selected)

        btn_add_robot = tk.Button(
            left_frame, text="+ Agregar robot", command=self.add_robot,
            bg=THEME["accent"], fg="white", font=THEME["font_small"],
            relief="flat", cursor="hand2", activebackground=THEME["accent_hover"], activeforeground="white"
        )
        btn_add_robot.pack(side="top", fill="x", padx=THEME["pad_sm"], pady=2)

        self.robot_status_label = tk.Label(
            left_frame, text="Selecciona un robot.", bg=THEME["bg_panel"],
            fg=THEME["text_secondary"], font=THEME["font_small"]
        )
        self.robot_status_label.pack(side="top", fill="x", padx=THEME["pad_sm"], pady=2)

        # Panel central: simulación
        center_frame = tk.LabelFrame(
            main_frame, text="  Simulación  ", bg=THEME["bg_panel"], fg=THEME["text"],
            font=THEME["font_title"], relief="flat", bd=0,
            highlightbackground=THEME["border"], highlightthickness=1
        )
        center_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        center_frame.rowconfigure(0, weight=1)
        center_frame.columnconfigure(0, weight=1)

        canvas_container = tk.Frame(center_frame, bg=THEME["bg_panel"])
        canvas_container.grid(row=0, column=0, sticky="nsew", padx=THEME["pad_sm"], pady=THEME["pad_sm"])
        canvas_container.rowconfigure(0, weight=1)
        canvas_container.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_container,
            width=500,
            height=320,
            bg=THEME["bg_canvas"],
            highlightthickness=0,
            scrollregion=(0, 0, 900, 600),
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        x_scroll = tk.Scrollbar(canvas_container, orient="horizontal", command=self.canvas.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll = tk.Scrollbar(canvas_container, orient="vertical", command=self.canvas.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        controls_frame = tk.Frame(center_frame, bg=THEME["bg_panel"])
        controls_frame.grid(row=1, column=0, sticky="ew", padx=THEME["pad_sm"], pady=THEME["pad_sm"])

        def _btn(txt, cmd, bg_color):
            return tk.Button(
                controls_frame, text=txt, command=cmd, bg=bg_color, fg="white",
                font=THEME["font_small"], relief="flat", cursor="hand2", padx=10, pady=4,
                activebackground=bg_color, activeforeground="white"
            )

        self.btn_start_simulation = _btn("Iniciar simulación", self.start_simulation, THEME["success"])
        self.btn_start_simulation.pack(side="left", padx=3)
        btn_report = _btn("Informe de desplazamientos", self.show_reports, THEME["accent"])
        btn_report.pack(side="left", padx=3)
        btn_manage = _btn("Gestionar productos", self.manage_products, THEME["info"])
        btn_manage.pack(side="left", padx=3)

        self.sim_status_label = tk.Label(
            controls_frame, text="Listo para simular.", bg=THEME["bg_panel"],
            fg=THEME["text_secondary"], font=THEME["font_small"]
        )
        self.sim_status_label.pack(side="left", padx=10)

        # Panel derecho: productos (con botón de actualización por lista)
        right_frame = tk.LabelFrame(
            main_frame, text="  Productos  ", bg=THEME["bg_panel"], fg=THEME["text"],
            font=THEME["font_title"], relief="flat", bd=0,
            highlightbackground=THEME["border"], highlightthickness=1
        )
        right_frame.grid(row=0, column=2, sticky="ns", padx=5, pady=5)

        # Bloque: productos almacenados (inicio)
        frame_initial = tk.Frame(right_frame, bg=THEME["bg_panel"])
        frame_initial.pack(fill="x", pady=(THEME["pad_sm"], 0))
        lbl_before = tk.Label(
            frame_initial, text="Almacenados (inicio):", bg=THEME["bg_panel"],
            fg=THEME["text"], font=THEME["font_small"]
        )
        lbl_before.pack(side="left")
        btn_refresh_initial = tk.Button(
            frame_initial, text="Actualizar", command=self.refresh_initial_list,
            bg=THEME["accent"], fg="white", font=("Segoe UI", 8), relief="flat",
            cursor="hand2", padx=6, pady=2, activebackground=THEME["accent_hover"], activeforeground="white"
        )
        btn_refresh_initial.pack(side="right")
        self.listbox_initial = tk.Listbox(
            frame_initial, height=6, width=38, bg=THEME["bg_panel"], fg=THEME["text"],
            font=THEME["font_small"], relief="flat", highlightthickness=0,
            selectbackground=THEME["accent"], selectforeground="white"
        )
        self.listbox_initial.pack(fill="x", padx=THEME["pad_sm"], pady=2)

        # Bloque: productos restantes
        frame_remaining = tk.Frame(right_frame, bg=THEME["bg_panel"])
        frame_remaining.pack(fill="x", pady=(THEME["pad_lg"], 0))
        lbl_after = tk.Label(
            frame_remaining, text="Restantes (tras recoger en A):", bg=THEME["bg_panel"],
            fg=THEME["text"], font=THEME["font_small"]
        )
        lbl_after.pack(side="left")
        btn_refresh_remaining = tk.Button(
            frame_remaining, text="Actualizar", command=self.refresh_remaining_list,
            bg=THEME["accent"], fg="white", font=("Segoe UI", 8), relief="flat",
            cursor="hand2", padx=6, pady=2, activebackground=THEME["accent_hover"], activeforeground="white"
        )
        btn_refresh_remaining.pack(side="right")
        self.listbox_remaining = tk.Listbox(
            frame_remaining, height=6, width=38, bg=THEME["bg_panel"], fg=THEME["text"],
            font=THEME["font_small"], relief="flat", highlightthickness=0,
            selectbackground=THEME["accent"], selectforeground="white"
        )
        self.listbox_remaining.pack(fill="x", padx=THEME["pad_sm"], pady=2)

        # Expansión
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

    # ------------------------------
    # Canvas y puntos
    # ------------------------------
    def setup_canvas(self):
        # Coordenadas
        self.origin = (80, 150)
        self.point_a = (240, 80)
        self.point_b = (420, 80)
        self.point_c = (420, 180)
        self.point_d = (240, 260)

        self.point_items = {}  # id_oval -> ("A"/"B"/"C"/"D", attr_name)
        self.point_labels = {}  # "A"/... -> text_item_id

        # Fondo y rejilla
        for x in range(0, 520, 20):
            self.canvas.create_line(x, 0, x, 340, fill=THEME["border"])
        for y in range(0, 340, 20):
            self.canvas.create_line(0, y, 520, y, fill=THEME["border"])

        # Estación de descanso
        self.canvas.create_rectangle(
            20, 110, 140, 290, outline=THEME["border"], dash=(3, 2), fill=THEME["bg_panel"]
        )
        self.canvas.create_text(80, 120, text="Estación\nrobots", font=THEME["font_title"])

        # Puntos principales
        self.canvas.create_oval(
            self.origin[0] - 10, self.origin[1] - 10,
            self.origin[0] + 10, self.origin[1] + 10,
            fill="lightblue"
        )
        self.canvas.create_text(self.origin[0], self.origin[1] + 20, text="Origen")

        a_oval = self.canvas.create_oval(
            self.point_a[0] - 10, self.point_a[1] - 10,
            self.point_a[0] + 10, self.point_a[1] + 10,
            fill="lightgreen"
        )
        a_text = self.canvas.create_text(self.point_a[0], self.point_a[1] - 15, text="Almacén (A)")

        b_oval = self.canvas.create_oval(
            self.point_b[0] - 10, self.point_b[1] - 10,
            self.point_b[0] + 10, self.point_b[1] + 10,
            fill="lightcoral"
        )
        b_text = self.canvas.create_text(self.point_b[0], self.point_b[1] - 20, text="Punto B")

        c_oval = self.canvas.create_oval(
            self.point_c[0] - 10, self.point_c[1] - 10,
            self.point_c[0] + 10, self.point_c[1] + 10,
            fill="#ffb347"
        )
        c_text = self.canvas.create_text(self.point_c[0], self.point_c[1] + 20, text="Punto C")

        d_oval = self.canvas.create_oval(
            self.point_d[0] - 10, self.point_d[1] - 10,
            self.point_d[0] + 10, self.point_d[1] + 10,
            fill="#9b59b6"
        )
        d_text = self.canvas.create_text(self.point_d[0], self.point_d[1] + 20, text="Punto D")

        # Registrar puntos para arrastrar
        self.point_items[a_oval] = ("A", "point_a")
        self.point_items[b_oval] = ("B", "point_b")
        self.point_items[c_oval] = ("C", "point_c")
        self.point_items[d_oval] = ("D", "point_d")
        self.point_labels["A"] = a_text
        self.point_labels["B"] = b_text
        self.point_labels["C"] = c_text
        self.point_labels["D"] = d_text

        self._dragging_point = None
        self._drag_offset = (0, 0)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

    def _dock_position_for_robot(self, robot_index: int):
        """Devuelve la posición de descanso para un robot según su índice."""
        col = robot_index % 2
        row = robot_index // 2
        x = 50 + col * 40
        y = 150 + row * 40
        return x, y

    def _on_canvas_press(self, event):
        # Detectar si se hizo clic sobre algún punto A/B/C/D
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        clicked = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)
        for item in clicked:
            if item in self.point_items:
                label, attr_name = self.point_items[item]
                bbox = self.canvas.bbox(item)
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2
                self._dragging_point = (item, label, attr_name)
                self._drag_offset = (x - cx, y - cy)
                return

    def _on_canvas_drag(self, event):
        if not self._dragging_point:
            return
        item, label, attr_name = self._dragging_point
        x = self.canvas.canvasx(event.x) - self._drag_offset[0]
        y = self.canvas.canvasy(event.y) - self._drag_offset[1]
        # Mover óvalo
        bbox = self.canvas.bbox(item)
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        dx = x - cx
        dy = y - cy
        self.canvas.move(item, dx, dy)
        # Mover etiqueta asociada
        text_id = self.point_labels.get(label)
        if text_id:
            self.canvas.move(text_id, dx, dy)
        # Actualizar coordenadas lógicas
        new_x = x
        new_y = y
        setattr(self, attr_name, (new_x, new_y))

    def _on_canvas_release(self, event):
        self._dragging_point = None

    # ------------------------------
    # Manejo de robots
    # ------------------------------
    def add_robot(self):
        robot = Robot(self.next_robot_id)
        self.next_robot_id += 1
        self.robots.append(robot)
        # Crear marcador gráfico del robot en su estación
        idx = len(self.robots) - 1
        rx, ry = self._dock_position_for_robot(idx)
        marker = self.canvas.create_rectangle(
            rx - 8, ry - 8,
            rx + 8, ry + 8,
            fill="#555555"
        )
        self.robot_markers[robot.robot_id] = marker
        self.refresh_robots_listbox()

    def refresh_robots_listbox(self):
        self.robots_listbox.delete(0, tk.END)
        for r in self.robots:
            status_text = "Disponible" if r.status == "disponible" else "En recorrido"
            color_text = "🟢" if r.status == "disponible" else "🟠"
            assigned = " (con lista)" if r.assigned_products else ""
            self.robots_listbox.insert(
                tk.END,
                f"Robot {r.robot_id} - {color_text} {status_text}{assigned}"
            )

    def get_selected_robot(self):
        sel = self.robots_listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        return self.robots[idx]

    def on_robot_selected(self, event=None):
        robot = self.get_selected_robot()
        if not robot:
            return

        # Ventana de opciones
        win = tk.Toplevel(self.root)
        win.title(f"Robot {robot.robot_id}")

        lbl = tk.Label(
            win,
            text=f"Robot {robot.robot_id}\nEstado: {robot.status}\n"
                 f"Productos asignados: {len(robot.assigned_products)}"
        )
        lbl.pack(padx=10, pady=10)

        btn_assign = tk.Button(
            win,
            text="Asignar lista de productos",
            command=lambda: [win.destroy(), self.assign_products_to_robot(robot)]
        )
        btn_assign.pack(fill="x", padx=10, pady=5)

        btn_close = tk.Button(win, text="Salir al menú", command=win.destroy)
        btn_close.pack(fill="x", padx=10, pady=5)

    # ------------------------------
    # Asignar productos a robot
    # ------------------------------
    def assign_products_to_robot(self, robot: Robot):
        products = get_all_products()
        if not products:
            messagebox.showwarning("Sin productos", "No hay productos en la base de datos.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Asignar productos - Robot {robot.robot_id}")

        lbl = tk.Label(win, text="Selecciona un producto y la cantidad, luego pulsa 'Agregar a lista'.")
        lbl.pack(padx=10, pady=5)

        # Tabla de productos
        columns = ("nombre", "stock")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=8)
        tree.heading("nombre", text="Nombre")
        tree.heading("stock", text="Stock actual")
        for p in products:
            tree.insert("", tk.END, iid=str(p["_id"]), values=(p["nombre"], p["stock"]))
        tree.pack(padx=10, pady=5, fill="x")

        qty_frame = tk.Frame(win)
        qty_frame.pack(padx=10, pady=5, fill="x")
        tk.Label(qty_frame, text="Cantidad:").pack(side="left")
        qty_var = tk.IntVar(value=1)
        qty_spin = tk.Spinbox(qty_frame, from_=1, to=1000, textvariable=qty_var, width=5)
        qty_spin.pack(side="left", padx=5)

        assigned_listbox = tk.Listbox(win, height=6, width=50)
        assigned_listbox.pack(padx=10, pady=5, fill="x")

        # Cargar ya asignados (si existían)
        for item in robot.assigned_products:
            assigned_listbox.insert(tk.END, f"{item['name']} x {item['qty']}")

        def add_to_assigned_real():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Selección", "Selecciona un producto.")
                return
            product_id_str = sel[0]
            qty = qty_var.get()
            if qty <= 0:
                messagebox.showwarning("Cantidad", "La cantidad debe ser mayor a 0.")
                return

            oid = self._get_oid(product_id_str)
            if not oid:
                messagebox.showerror("Error", "ID de producto inválido.")
                return

            prod = products_coll.find_one({"_id": oid})
            if not prod:
                messagebox.showerror("Error", "Producto no encontrado en la base de datos.")
                return

            disponible = prod["stock"] - self._reserved_stock(oid)
            if qty > disponible:
                messagebox.showerror("Stock insuficiente", f"Stock disponible: {disponible}. Intentas: {qty}.")
                return

            # Añadir o acumular
            existing = next((x for x in robot.assigned_products if x["product_id"] == oid), None)
            if existing:
                existing["qty"] += qty
            else:
                robot.assigned_products.append(
                    {"product_id": oid, "name": prod["nombre"], "qty": qty}
                )

            # Refrescar listbox
            assigned_listbox.delete(0, tk.END)
            for item in robot.assigned_products:
                assigned_listbox.insert(tk.END, f"{item['name']} x {item['qty']}")

        btn_add = tk.Button(win, text="Agregar a lista", command=add_to_assigned_real)
        btn_add.pack(padx=10, pady=5)

        def close_and_refresh():
            self.refresh_robots_listbox()
            win.destroy()

        btn_done = tk.Button(win, text="Aceptar", command=close_and_refresh)
        btn_done.pack(padx=10, pady=5)

    # ------------------------------
    # Listas de productos (GUI)
    # ------------------------------
    def refresh_initial_list(self):
        """Actualiza el snapshot de inicio desde la DB y redibuja la lista 'Almacenados (inicio)'."""
        self.initial_products_snapshot = get_all_products()
        self.listbox_initial.delete(0, tk.END)
        for p in self.initial_products_snapshot:
            self.listbox_initial.insert(tk.END, f"{p['nombre']}: {p['stock']}")

    def refresh_remaining_list(self):
        """Actualiza la lista 'Restantes' desde el estado actual de la DB."""
        current = get_all_products()
        self.listbox_remaining.delete(0, tk.END)
        for p in current:
            self.listbox_remaining.insert(tk.END, f"{p['nombre']}: {p['stock']}")

    def refresh_product_lists(self):
        """Actualiza ambas listas: inicio (snapshot) y restantes (DB)."""
        self.listbox_initial.delete(0, tk.END)
        for p in self.initial_products_snapshot:
            self.listbox_initial.insert(tk.END, f"{p['nombre']}: {p['stock']}")

        current = get_all_products()
        self.listbox_remaining.delete(0, tk.END)
        for p in current:
            self.listbox_remaining.insert(tk.END, f"{p['nombre']}: {p['stock']}")

    # ------------------------------
    # Simulación
    # ------------------------------
    def start_simulation(self):
        # Elegir robot que va a desplazarse
        available_robots = [r for r in self.robots if r.status == "disponible"]
        if not available_robots:
            messagebox.showwarning("Sin robots", "No hay robots disponibles.")
            return

        # Ventana para elegir robot y destino
        win = tk.Toplevel(self.root)
        win.title("Seleccionar robot y destino")
        win.resizable(False, False)

        tk.Label(win, text="Robot disponible:", font=("Segoe UI", 9, "bold")).pack(
            padx=10, pady=(10, 2)
        )

        robot_var = tk.StringVar()
        combo_robot = ttk.Combobox(win, textvariable=robot_var, state="readonly", width=20)
        combo_values = [f"Robot {r.robot_id}" for r in available_robots]
        combo_robot["values"] = combo_values
        if combo_values:
            combo_robot.current(0)
        combo_robot.pack(padx=10, pady=(0, 8))

        tk.Label(win, text="Destino del recorrido:", font=("Segoe UI", 9, "bold")).pack(
            padx=10, pady=(5, 2)
        )

        dest_var = tk.StringVar()
        combo_dest = ttk.Combobox(win, textvariable=dest_var, state="readonly", width=20)
        combo_dest["values"] = ["Punto B", "Punto C", "Punto D"]
        combo_dest.current(0)
        combo_dest.pack(padx=10, pady=(0, 10))

        def on_accept():
            sel_robot = robot_var.get()
            sel_dest = dest_var.get()
            if not sel_robot:
                messagebox.showwarning("Selección", "Selecciona un robot.")
                return
            rid = int(sel_robot.replace("Robot ", ""))
            robot = next(r for r in self.robots if r.robot_id == rid)

            if not robot.assigned_products:
                messagebox.showwarning(
                    "Sin lista",
                    "Este robot no tiene una lista de productos asignada."
                )
                return

            # Definir destino
            if sel_dest == "Punto B":
                robot.destination_label = "Punto B"
                robot.destination_point = self.point_b
            elif sel_dest == "Punto C":
                robot.destination_label = "Punto C"
                robot.destination_point = self.point_c
            else:
                robot.destination_label = "Punto D"
                robot.destination_point = self.point_d

            win.destroy()
            self.run_simulation_for_robot(robot)

        btn_ok = tk.Button(win, text="Iniciar", command=on_accept)
        btn_ok.pack(padx=10, pady=10)

    def run_simulation_for_robot(self, robot: Robot):
        # Marcar robot en recorrido
        robot.status = "en_recorrido"
        self.refresh_robots_listbox()
        self.sim_status_label.config(text=f"Robot {robot.robot_id} en movimiento...")

        marker_id = self.robot_markers.get(robot.robot_id)
        if marker_id is None:
            return

        # Posición actual del robot (en estación)
        x0, y0, x1, y1 = self.canvas.coords(marker_id)
        start_pos = ((x0 + x1) / 2, (y0 + y1) / 2)

        # Secuencia: estación → A → destino (B/C/D) → regreso a estación
        drop_point = robot.destination_point or self.point_b
        # hallar posición de estación original por índice
        idx = self.robots.index(robot)
        dock_x, dock_y = self._dock_position_for_robot(idx)
        path = [start_pos, self.point_a, drop_point, (dock_x, dock_y)]

        def move_step(i, cur_x, cur_y, target_x, target_y, stage_index):
            # Movimiento lineal simple
            if abs(cur_x - target_x) < 2 and abs(cur_y - target_y) < 2:
                # Llegó al waypoint
                if stage_index == 1:
                    # Llegó al punto A (Almacén): actualizar stock
                    try:
                        update_stock_for_pick(robot.assigned_products)
                        self.refresh_product_lists()
                        messagebox.showinfo(
                            "Recolección completada",
                            f"Robot {robot.robot_id} ha recogido los productos en el Almacén (A)."
                        )
                    except ValueError as e:
                        messagebox.showerror("Error de stock", str(e))
                        # Terminar simulación con error y liberar robot
                        robot.status = "disponible"
                        self.sim_status_label.config(text="Simulación cancelada por error de stock.")
                        self.refresh_robots_listbox()
                        return
                if stage_index == 2:
                    # Llegó al punto de destino (entrega de productos)
                    messagebox.showinfo(
                        "Entrega completada",
                        f"Robot {robot.robot_id} ha dejado los productos en {robot.destination_label}.\n"
                        f"Ahora regresa a su estación de descanso."
                    )
                if stage_index == 3:
                    # Llegó de regreso a su estación: fin de recorrido
                    log_run(robot, robot.assigned_products)
                    robot.status = "disponible"
                    # Limpia lista de productos del robot para siguiente asignación
                    robot.assigned_products = []
                    self.refresh_robots_listbox()
                    self.sim_status_label.config(
                        text=f"Robot {robot.robot_id} finalizó el recorrido en su estación."
                    )
                    messagebox.showinfo(
                        "Recorrido completado",
                        f"Robot {robot.robot_id} ha regresado a su estación de descanso."
                    )
                    return

                # Siguiente tramo
                next_stage = stage_index + 1
                if next_stage < len(path):
                    nx, ny = path[next_stage]
                    self.root.after(
                        80,
                        lambda: move_step(0, path[stage_index][0], path[stage_index][1], nx, ny, next_stage)
                    )
                return

            # Interpolación simple más lenta para apreciar el movimiento
            step_size = 2
            dx = target_x - cur_x
            dy = target_y - cur_y
            dist = max((dx ** 2 + dy ** 2) ** 0.5, 0.0001)
            nx = cur_x + step_size * dx / dist
            ny = cur_y + step_size * dy / dist

            self.canvas.coords(
                marker_id,
                nx - 8, ny - 8,
                nx + 8, ny + 8
            )

            self.root.after(
                80,
                lambda: move_step(i + 1, nx, ny, target_x, target_y, stage_index)
            )

        # Iniciar primer tramo desde la estación hasta A
        sx, sy = start_pos
        ax, ay = self.point_a
        move_step(0, sx, sy, ax, ay, 1)

    # ------------------------------
    # Gestión de productos
    # ------------------------------
    def manage_products(self):
        win = tk.Toplevel(self.root)
        win.title("Gestionar productos")
        win.geometry("600x500")

        tk.Label(win, text="Productos registrados", font=("Segoe UI", 12, "bold")).pack(pady=10)

        products = get_all_products()
        columns = ("nombre", "stock")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=10)
        tree.heading("nombre", text="Nombre")
        tree.heading("stock", text="Stock")
        for p in products:
            tree.insert("", tk.END, iid=str(p["_id"]), values=(p["nombre"], p["stock"]))
        tree.pack(padx=10, pady=10, fill="both", expand=True)

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)

        def add_product():
            name = simpledialog.askstring("Nuevo producto", "Nombre del producto:")
            if not name:
                return
            stock = simpledialog.askinteger("Stock inicial", "Cantidad inicial:", minvalue=0)
            if stock is None:
                return
            products_coll.insert_one({"nombre": name, "stock": stock})
            self.refresh_product_lists()
            win.destroy()
            self.manage_products()

        def update_stock():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Selección", "Selecciona un producto.")
                return
            oid = self._get_oid(sel[0])
            if not oid:
                return
            prod = products_coll.find_one({"_id": oid})
            if not prod:
                return
            new_stock = simpledialog.askinteger("Actualizar stock", f"Nuevo stock para {prod['nombre']}:", minvalue=0, initialvalue=prod["stock"])
            if new_stock is not None:
                products_coll.update_one({"_id": oid}, {"$set": {"stock": new_stock}})
                self.refresh_product_lists()
                win.destroy()
                self.manage_products()

        def delete_product():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Selección", "Selecciona un producto.")
                return
            oid = self._get_oid(sel[0])
            if not oid:
                return
            prod = products_coll.find_one({"_id": oid})
            if not prod:
                return
            if messagebox.askyesno("Confirmar", f"¿Eliminar {prod['nombre']}?"):
                products_coll.delete_one({"_id": oid})
                self.refresh_product_lists()
                win.destroy()
                self.manage_products()

        def view_info():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Selección", "Selecciona un producto.")
                return
            oid = self._get_oid(sel[0])
            if not oid:
                return
            prod = products_coll.find_one({"_id": oid})
            if not prod:
                return
            reserved = self._reserved_stock(oid)
            available = prod["stock"] - reserved
            info = f"Nombre: {prod['nombre']}\nStock total: {prod['stock']}\nReservado: {reserved}\nDisponible: {available}"
            messagebox.showinfo("Información del producto", info)

        tk.Button(btn_frame, text="Agregar", command=add_product, bg=THEME["success"], fg="white", font=THEME["font_small"], relief="flat", cursor="hand2").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Editar stock", command=update_stock, bg=THEME["accent"], fg="white", font=THEME["font_small"], relief="flat", cursor="hand2").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Eliminar", command=delete_product, bg=THEME["danger"], fg="white", font=THEME["font_small"], relief="flat", cursor="hand2").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Ver info", command=view_info, bg=THEME["info"], fg="white", font=THEME["font_small"], relief="flat", cursor="hand2").pack(side="left", padx=5)
    
    # ------------------------------
    # Informe de recorridos
    # ------------------------------
    def show_reports(self):
        robots_ids = [r.robot_id for r in self.robots]
        if not robots_ids:
            messagebox.showinfo("Sin robots", "No hay robots registrados.")
            return

        win = tk.Toplevel(self.root)
        win.title("Informe de desplazamientos")
        win.geometry("600x400")

        tk.Label(win, text="Selecciona un robot:", font=("Segoe UI", 9, "bold")).pack(
            padx=10, pady=(10, 2)
        )

        robot_var = tk.StringVar()
        combo = ttk.Combobox(win, textvariable=robot_var, state="readonly", width=20)
        combo_vals = [f"Robot {rid}" for rid in robots_ids]
        combo["values"] = combo_vals
        if combo_vals:
            combo.current(0)
        combo.pack(padx=10, pady=(0, 8))

        frame_lists = tk.Frame(win)
        frame_lists.pack(fill="both", expand=True, padx=10, pady=5)
        frame_lists.columnconfigure(0, weight=1)
        frame_lists.columnconfigure(1, weight=2)
        frame_lists.rowconfigure(0, weight=1)

        runs_list = tk.Listbox(frame_lists)
        runs_list.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        detail_text = tk.Text(frame_lists, wrap="word")
        detail_text.grid(row=0, column=1, sticky="nsew")

        def load_runs(*_):
            runs_list.delete(0, tk.END)
            detail_text.delete("1.0", tk.END)
            sel = robot_var.get()
            if not sel:
                return
            rid = int(sel.replace("Robot ", ""))
            # Consultar recorridos de MongoDB
            cursor = runs_coll.find({"robot_id": rid}).sort("timestamp", -1)
            self._current_runs = list(cursor)
            if not self._current_runs:
                detail_text.insert("1.0", f"Robot {rid} no tiene recorridos registrados.")
                return
            for i, r in enumerate(self._current_runs):
                ts = r.get("timestamp")
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "sin fecha"
                dest = r.get("dropoff_point", "?")
                runs_list.insert(tk.END, f"{i+1}. {ts_str} → {dest}")

        def show_detail(event):
            sel = runs_list.curselection()
            if not sel:
                return
            idx = sel[0]
            run = self._current_runs[idx]
            detail_text.delete("1.0", tk.END)
            ts = run.get("timestamp")
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "sin fecha"
            lines = []
            lines.append(f"Robot ID: {run.get('robot_id')}")
            lines.append(f"Fecha y hora: {ts_str}")
            lines.append(f"Origen: {run.get('from_point')}")
            lines.append(f"Punto de recogida: {run.get('pickup_point')}")
            lines.append(f"Punto de entrega: {run.get('dropoff_point')}")
            lines.append(f"Finalizó en estación: {run.get('finished_at_station')}")
            lines.append("")
            lines.append("Productos movidos:")
            for p in run.get("productos", []):
                lines.append(f"  - {p.get('nombre')} x {p.get('cantidad')}")
            detail_text.insert("1.0", "\n".join(lines))

        combo.bind("<<ComboboxSelected>>", load_runs)
        runs_list.bind("<<ListboxSelect>>", show_detail)

        load_runs()


# ==========================
# MAIN
# ==========================

def main():
    root = tk.Tk()
    app = MiRSimulatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()