"""
Wizard101 Pet Genetics Research
Tkinter + SQLite desktop research tool.

The original database tables are retained for backward compatibility.
Derby observations are stored in separate tables so Combat slot numbering
and historical records remain untouched.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3, json, csv, uuid, shutil
from pathlib import Path
from datetime import datetime

DATA_DIR = Path.home() / "Wizard101PetGenetics"
DATA_DIR.mkdir(exist_ok=True)
DB = DATA_DIR / "pet_genetics.sqlite3"
N_A = "N/A"

def db():
    """Return a foreign-key-enabled SQLite connection."""
    c = sqlite3.connect(DB)
    c.execute("PRAGMA foreign_keys=ON")
    return c

def rows(sql, args=()):
    """Fetch rows using a short-lived database connection."""
    with db() as c:
        return c.execute(sql, args).fetchall()

def init():
    """Create the original schema and safely add Derby-specific tables."""
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS talents(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE,
            category TEXT, school TEXT, rarity TEXT, status TEXT, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS pets(id TEXT PRIMARY KEY,name TEXT,notes TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS pet_talents(
            pet_id TEXT REFERENCES pets(id) ON DELETE CASCADE,slot INTEGER,
            talent_id INTEGER REFERENCES talents(id),manifested INTEGER,
            PRIMARY KEY(pet_id,slot),UNIQUE(pet_id,talent_id)
        );
        CREATE TABLE IF NOT EXISTS experiments(
            id TEXT PRIMARY KEY,name TEXT,parent_a TEXT REFERENCES pets(id),
            parent_b TEXT REFERENCES pets(id),contributor TEXT,notes TEXT,created TEXT
        );
        CREATE TABLE IF NOT EXISTS experiment_talents(
            experiment_id TEXT REFERENCES experiments(id) ON DELETE CASCADE,
            parent_side TEXT,slot INTEGER,talent_id INTEGER REFERENCES talents(id),
            manifested INTEGER,PRIMARY KEY(experiment_id,parent_side,slot)
        );
        CREATE TABLE IF NOT EXISTS hatches(
            id TEXT PRIMARY KEY,experiment_id TEXT REFERENCES experiments(id) ON DELETE CASCADE,
            child_name TEXT,hatch_date TEXT,contributor TEXT,notes TEXT,created TEXT
        );
        CREATE TABLE IF NOT EXISTS hatch_talents(
            hatch_id TEXT REFERENCES hatches(id) ON DELETE CASCADE,slot INTEGER,
            talent_id INTEGER REFERENCES talents(id),manifested INTEGER,
            PRIMARY KEY(hatch_id,slot),UNIQUE(hatch_id,talent_id)
        );
        -- Derby data is separate: no changes to existing Combat keys or slots.
        CREATE TABLE IF NOT EXISTS pet_derby_talents(
            pet_id TEXT REFERENCES pets(id) ON DELETE CASCADE,slot INTEGER,
            talent_id INTEGER REFERENCES talents(id),manifested INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(pet_id,slot),UNIQUE(pet_id,talent_id)
        );
        CREATE TABLE IF NOT EXISTS experiment_derby_talents(
            experiment_id TEXT REFERENCES experiments(id) ON DELETE CASCADE,
            parent_side TEXT,slot INTEGER,talent_id INTEGER REFERENCES talents(id),
            manifested INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(experiment_id,parent_side,slot)
        );
        CREATE TABLE IF NOT EXISTS hatch_derby_talents(
            hatch_id TEXT REFERENCES hatches(id) ON DELETE CASCADE,slot INTEGER,
            talent_id INTEGER REFERENCES talents(id),manifested INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(hatch_id,slot),UNIQUE(hatch_id,talent_id)
        );
        """)
        # Add Derby manifested flags to existing databases without disturbing saved records.
        for table in ("pet_derby_talents", "experiment_derby_talents", "hatch_derby_talents"):
            columns = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
            if "manifested" not in columns:
                c.execute(f"ALTER TABLE {table} ADD COLUMN manifested INTEGER NOT NULL DEFAULT 0")
        # Retain the previous starter entries as a fallback if no catalog exists.
        c.execute("UPDATE talents SET category='Combat' WHERE category IS NULL OR TRIM(category)=''")
        # The former starter catalog incorrectly labeled Couch Potato as a Combat
        # talent. Keep any old referenced row for historical integrity, but do not
        # count or offer it as one of the authoritative Combat catalog entries.
        c.execute("UPDATE talents SET category='Legacy' WHERE name='Couch Potato' COLLATE NOCASE")
        # Seed/update the bundled complete catalog without deleting research records.
        bundled = Path(__file__).with_name("talent_catalog_starter.csv")
        if bundled.exists():
            with bundled.open(encoding="utf-8-sig", newline="") as catalog_file:
                for item in csv.DictReader(catalog_file):
                    name = (item.get("name") or "").strip()
                    if not name:
                        continue
                    c.execute("""INSERT INTO talents(name,category,school,rarity,status,notes)
                        VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                        category=excluded.category,school=excluded.school,rarity=excluded.rarity,
                        status=excluded.status,notes=excluded.notes""",
                        (name,item.get("category") or "Combat",item.get("school") or "",
                         item.get("rarity") or "",item.get("status") or "Active",item.get("notes") or ""))

def catalog(category):
    """Return talent names for one category only."""
    return [r[0] for r in rows(
        "SELECT name FROM talents WHERE category=? ORDER BY name COLLATE NOCASE", (category,)
    )]

def talent_id(name, category):
    """Resolve a catalog name while enforcing its category."""
    r = rows("SELECT id FROM talents WHERE name=? COLLATE NOCASE AND category=?", (name, category))
    if not r:
        raise ValueError(f"'{name}' is not in the {category} catalog.")
    return r[0][0]

class SlotEditor(ttk.Frame):
    """Vertically numbered talent slots with category-specific selectors."""
    def __init__(self, master, category, count=10, manifested=False, default=""):
        super().__init__(master)
        self.category = category
        self.manifested = manifested
        self.items = []
        ttk.Label(self, text=f"{category} talents", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(4, 3))
        values = catalog(category)
        if category == "Derby":
            values = [N_A] + values
        for i in range(count):
            ttk.Label(self, text=f"{i+1}.", width=4).grid(row=i+1,column=0,sticky="w",pady=2)
            var = tk.StringVar(value=default)
            cb = ttk.Combobox(self, textvariable=var, values=values, width=38)
            cb.grid(row=i+1,column=1,sticky="ew",padx=4,pady=2)
            mv = tk.BooleanVar(value=False)
            if manifested:
                ttk.Checkbutton(self,text="Manifested",variable=mv).grid(row=i+1,column=2,sticky="w")
            self.items.append((var,mv,cb))
        self.columnconfigure(1,weight=1)

    def refresh_values(self):
        """Refresh choices after catalog import."""
        vals = catalog(self.category)
        if self.category == "Derby":
            vals = [N_A] + vals
        for _,_,cb in self.items:
            cb["values"] = vals

    def get_values(self, required=False, allowed=None):
        """Validate and return (slot, talent_id, manifested) tuples."""
        output, seen = [], set()
        for i,(var,mv,_) in enumerate(self.items,1):
            name = var.get().strip()
            if self.category == "Derby" and (not name or name == N_A):
                continue
            if not name:
                if required:
                    raise ValueError(f"Fill Combat talent slot {i}.")
                continue
            key = name.casefold()
            if key in seen:
                raise ValueError(f"Duplicate {self.category} talent: {name}")
            seen.add(key)
            tid = talent_id(name,self.category)
            if allowed is not None and key not in allowed:
                raise ValueError(f"{self.category} talent '{name}' is not in the selected experiment's parent pool.")
            output.append((i,tid,int(bool(mv.get())) if self.manifested else 0))
        # Combat and Derby each have their own five-manifested-talent limit.
        manifested_count = sum(
            1 for var, mv, _ in self.items
            if self.manifested and bool(mv.get()) and var.get().strip()
            and var.get().strip() != N_A
        )
        if manifested_count > 5:
            raise ValueError(f"A pet can have at most 5 manifested {self.category} talents.")
        return output

    def set_values(self, data):
        """Load ordered (slot, name, manifested) records into the editor."""
        by_slot = {r[0]:r for r in data}
        for i,(var,mv,_) in enumerate(self.items,1):
            r = by_slot.get(i)
            var.set(r[1] if r else (N_A if self.category=="Derby" else ""))
            mv.set(bool(r[2]) if r and len(r)>2 else False)

    def clear(self):
        """Reset all fields to their default values."""
        for var,mv,_ in self.items:
            var.set(N_A if self.category=="Derby" else "")
            mv.set(False)

class App(tk.Tk):
    """Main window and workflow controller for pet genetics research."""
    def __init__(self):
        super().__init__()
        self.title("Wizard101 Pet Genetics Research")
        self.geometry("1320x940")
        self.minsize(1100,780)
        self.edit_parent_id = self.edit_exp_id = self.edit_hatch_id = None
        self.parent_choice = {}; self.exp_choice = {}
        self.tabs = ttk.Notebook(self); self.tabs.pack(fill="both",expand=True,padx=8,pady=8)
        self.make_parents()
        self.make_experiments()
        self.make_hatches()
        self.make_family_tree()
        self.make_analytics()
        self.make_catalog()
        self.make_data()
        self.refresh()

    def tab(self,title):
        f=ttk.Frame(self.tabs,padding=10); self.tabs.add(f,text=title); return f

    def entry(self, parent, label, var, width=65):
        row=ttk.Frame(parent); row.pack(fill="x",pady=3)
        ttk.Label(row,text=label,width=17).pack(side="left")
        ttk.Entry(row,textvariable=var,width=width).pack(side="left",fill="x",expand=True)

    def make_parents(self):
        f=self.tab("Parents")
        left=ttk.Frame(f);left.pack(side="left",fill="y")
        ttk.Label(left,text="Saved parents").pack(anchor="w")
        self.parents=ttk.Treeview(left,columns=("name",),show="headings",height=28)
        self.parents.heading("name",text="Pet");self.parents.column("name",width=220)
        self.parents.pack(fill="y");self.parents.bind("<<TreeviewSelect>>",self.load_parent)
        right=ttk.Frame(f,padding=10);right.pack(side="left",fill="both",expand=True)
        self.pname=tk.StringVar();self.pnotes=tk.StringVar()
        self.entry(right,"Pet name",self.pname);self.entry(right,"Notes",self.pnotes)
        ttk.Label(right,text="Combat and Derby each support up to 5 manifested talents. Empty Derby slots default to N/A.").pack(anchor="w",pady=5)
        editors=ttk.Frame(right);editors.pack(fill="both",expand=True)
        self.pslots=SlotEditor(editors,"Combat",manifested=True);self.pslots.pack(side="left",fill="both",expand=True,padx=(0,12))
        self.pderby=SlotEditor(editors,"Derby",manifested=True,default=N_A);self.pderby.pack(side="left",fill="both",expand=True)
        bar=ttk.Frame(right);bar.pack(anchor="w",pady=8)
        ttk.Button(bar,text="Save new parent",command=self.save_parent).pack(side="left",padx=3)
        ttk.Button(bar,text="Update selected",command=self.update_parent).pack(side="left",padx=3)
        ttk.Button(bar,text="Clear",command=self.clear_parent).pack(side="left",padx=3)
        ttk.Button(bar,text="Delete",command=self.delete_parent).pack(side="left",padx=3)
        self.pstatus=ttk.Label(right);self.pstatus.pack(anchor="w")

    def load_parent(self,event=None):
        sel=self.parents.selection()
        if not sel:return
        pid=sel[0];self.edit_parent_id=pid
        p=rows("SELECT name,notes FROM pets WHERE id=?",(pid,))
        if not p:return
        self.pname.set(p[0][0]);self.pnotes.set(p[0][1] or "")
        self.pslots.set_values(rows("""SELECT pt.slot,t.name,pt.manifested FROM pet_talents pt
            JOIN talents t ON t.id=pt.talent_id WHERE pt.pet_id=? ORDER BY pt.slot""",(pid,)))
        self.pderby.set_values(rows("""SELECT d.slot,t.name,d.manifested FROM pet_derby_talents d
            JOIN talents t ON t.id=d.talent_id WHERE d.pet_id=? ORDER BY d.slot""",(pid,)))
        self.pstatus.config(text="Loaded selected parent for editing.")

    def clear_parent(self):
        self.edit_parent_id=None
        if self.parents.selection(): self.parents.selection_remove(self.parents.selection())
        self.pname.set("");self.pnotes.set("");self.pslots.clear();self.pderby.clear()
        self.pstatus.config(text="")

    def save_parent(self):
        self._save_parent(None)

    def update_parent(self):
        if not self.edit_parent_id:
            messagebox.showwarning("Select parent","Select a saved parent to update.");return
        self._save_parent(self.edit_parent_id)

    def _save_parent(self,pid):
        is_edit = pid is not None
        try:
            name=self.pname.get().strip()
            if not name:raise ValueError("Enter a pet name.")
            combat=self.pslots.get_values(required=True);derby=self.pderby.get_values()
            pid=pid or str(uuid.uuid4())
            with db() as c:
                if is_edit:
                    c.execute("UPDATE pets SET name=?,notes=? WHERE id=?",(name,self.pnotes.get(),pid))
                    c.execute("DELETE FROM pet_talents WHERE pet_id=?",(pid,))
                    c.execute("DELETE FROM pet_derby_talents WHERE pet_id=?",(pid,))
                else:
                    c.execute("INSERT INTO pets VALUES(?,?,?,?)",(pid,name,self.pnotes.get(),datetime.now().isoformat()))
                c.executemany("INSERT INTO pet_talents VALUES(?,?,?,?)",[(pid,*x) for x in combat])
                c.executemany("INSERT INTO pet_derby_talents (pet_id,slot,talent_id,manifested) VALUES(?,?,?,?)",[(pid,s,t,m) for s,t,m in derby])
            self.refresh();self.pstatus.config(text="Parent updated." if is_edit else "Parent saved.")
            self.edit_parent_id=pid
        except Exception as e:messagebox.showerror("Parent not saved",str(e))

    def delete_parent(self):
        pid=self.edit_parent_id or (self.parents.selection()[0] if self.parents.selection() else None)
        if not pid:return
        refs=rows("SELECT COUNT(*) FROM experiments WHERE parent_a=? OR parent_b=?",(pid,pid))[0][0]
        if refs:
            messagebox.showwarning("Parent is in use",f"This parent is referenced by {refs} experiment(s). Delete or reassign those experiments first. No data was deleted.");return
        if not messagebox.askyesno("Delete parent","Permanently delete this parent and its recorded Combat/Derby talents?"):return
        with db() as c:c.execute("DELETE FROM pets WHERE id=?",(pid,))
        self.clear_parent();self.refresh()

    def make_experiments(self):
        f=self.tab("Experiments")
        self.ename=tk.StringVar();self.ea=tk.StringVar();self.eb=tk.StringVar();self.econ=tk.StringVar();self.enotes=tk.StringVar()
        for label,var in [("Experiment name",self.ename),("Parent 1",self.ea),("Parent 2",self.eb),("Contributor",self.econ),("Notes",self.enotes)]:
            row=ttk.Frame(f);row.pack(fill="x",pady=3);ttk.Label(row,text=label,width=17).pack(side="left")
            if label.startswith("Parent"):
                cb=ttk.Combobox(row,textvariable=var,state="readonly");cb.pack(side="left",fill="x",expand=True)
                if label=="Parent 1":self.eacb=cb
                else:self.ebcb=cb
            else:ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True)
        bar=ttk.Frame(f);bar.pack(anchor="e",pady=6)
        ttk.Button(bar,text="Save new experiment",command=self.save_experiment).pack(side="left",padx=3)
        ttk.Button(bar,text="Update selected",command=self.update_experiment).pack(side="left",padx=3)
        ttk.Button(bar,text="Clear",command=self.clear_experiment).pack(side="left",padx=3)
        ttk.Button(bar,text="Delete selected",command=self.delete_experiment).pack(side="left",padx=3)
        self.exptree=ttk.Treeview(f,columns=("pair","contributor"),show="headings",height=20)
        self.exptree.heading("pair",text="Experiment / parent pair");self.exptree.heading("contributor",text="Contributor")
        self.exptree.column("pair",width=800);self.exptree.pack(fill="both",expand=True)
        self.exptree.bind("<<TreeviewSelect>>",self.load_experiment)

    def _experiment_values(self):
        a=self.parent_choice.get(self.ea.get());b=self.parent_choice.get(self.eb.get())
        if not self.ename.get().strip() or not a or not b:raise ValueError("Enter a name and select both parents.")
        if a==b:raise ValueError("Choose two distinct parent pets.")
        if len(rows("SELECT * FROM pet_talents WHERE pet_id=?",(a,)))!=10 or len(rows("SELECT * FROM pet_talents WHERE pet_id=?",(b,)))!=10:
            raise ValueError("Both parents must have ten Combat talents.")
        return a,b

    def save_experiment(self):
        try:
            a,b=self._experiment_values();eid=str(uuid.uuid4())
            with db() as c:
                c.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?)",(eid,self.ename.get().strip(),a,b,self.econ.get(),self.enotes.get(),datetime.now().isoformat()))
                self.snapshot_parents(c,eid,a,b)
            self.edit_exp_id=None
            self.refresh();messagebox.showinfo("Saved","Experiment and both-category parent snapshots saved.")
        except Exception as e:messagebox.showerror("Experiment not saved",str(e))

    def snapshot_parents(self,c,eid,a,b):
        """Copy current parent pools into immutable experiment snapshots."""
        for side,pid in (("A",a),("B",b)):
            c.execute("""INSERT INTO experiment_talents
                SELECT ?,?,slot,talent_id,manifested FROM pet_talents WHERE pet_id=?""",(eid,side,pid))
            c.execute("""INSERT INTO experiment_derby_talents
                SELECT ?,?,slot,talent_id,manifested FROM pet_derby_talents WHERE pet_id=?""",(eid,side,pid))

    def load_experiment(self,event=None):
        sel=self.exptree.selection()
        if not sel:return
        eid=sel[0];self.edit_exp_id=eid
        r=rows("SELECT name,parent_a,parent_b,contributor,notes FROM experiments WHERE id=?",(eid,))
        if not r:return
        n,a,b,co,no=r[0];self.ename.set(n);self.econ.set(co or "");self.enotes.set(no or "")
        self.ea.set(next((k for k,v in self.parent_choice.items() if v==a),""))
        self.eb.set(next((k for k,v in self.parent_choice.items() if v==b),""))

    def clear_experiment(self):
        self.edit_exp_id=None
        if self.exptree.selection():self.exptree.selection_remove(self.exptree.selection())
        for v in (self.ename,self.ea,self.eb,self.econ,self.enotes):v.set("")

    def update_experiment(self):
        if not self.edit_exp_id:
            messagebox.showwarning("Select experiment","Select an experiment to update.");return
        try:
            a,b=self._experiment_values();eid=self.edit_exp_id
            with db() as c:
                previous = c.execute("SELECT parent_a,parent_b FROM experiments WHERE id=?",(eid,)).fetchone()
                c.execute("UPDATE experiments SET name=?,parent_a=?,parent_b=?,contributor=?,notes=? WHERE id=?",
                          (self.ename.get().strip(),a,b,self.econ.get(),self.enotes.get(),eid))
                # Metadata-only edits preserve the original historical snapshots.
                # Change snapshots only when the experiment's actual parent pair changes.
                if previous and (previous[0] != a or previous[1] != b):
                    c.execute("DELETE FROM experiment_talents WHERE experiment_id=?",(eid,))
                    c.execute("DELETE FROM experiment_derby_talents WHERE experiment_id=?",(eid,))
                    self.snapshot_parents(c,eid,a,b)
            self.refresh();messagebox.showinfo("Updated","Experiment updated. Existing hatch records remain linked; their offspring snapshots are preserved.")
        except Exception as e:messagebox.showerror("Update failed",str(e))

    def delete_experiment(self):
        eid=self.edit_exp_id or (self.exptree.selection()[0] if self.exptree.selection() else None)
        if not eid:return
        count=rows("SELECT COUNT(*) FROM hatches WHERE experiment_id=?",(eid,))[0][0]
        msg=f"Delete this experiment and its two parent talent snapshots? {count} associated hatch record(s), including their Combat and Derby talents, will also be deleted."
        if not messagebox.askyesno("Delete experiment",msg):return
        with db() as c:c.execute("DELETE FROM experiments WHERE id=?",(eid,))
        self.clear_experiment();self.refresh()

    def make_hatches(self):
        f=self.tab("Hatch Records")
        self.hexp=tk.StringVar();self.hname=tk.StringVar();self.hdate=tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"));self.hcon=tk.StringVar();self.hnotes=tk.StringVar()
        row=ttk.Frame(f);row.pack(fill="x",pady=3);ttk.Label(row,text="Experiments",width=17).pack(side="left")
        self.hcb=ttk.Combobox(row,textvariable=self.hexp,state="readonly");self.hcb.pack(side="left",fill="x",expand=True);self.hcb.bind("<<ComboboxSelected>>",self.load_allowed_pool)
        for label,var in [("Offspring name",self.hname),("Hatch date",self.hdate),("Contributor",self.hcon),("Notes",self.hnotes)]:self.entry(f,label,var)
        ttk.Label(f,text="Combat and Derby use separate parent pools and separate five-manifested limits. Derby N/A slots are ignored.").pack(anchor="w",pady=4)
        editors=ttk.Frame(f);editors.pack(fill="both",expand=True)
        self.hslots=SlotEditor(editors,"Combat",manifested=True);self.hslots.pack(side="left",fill="both",expand=True,padx=(0,12))
        self.hderby=SlotEditor(editors,"Derby",manifested=True,default=N_A);self.hderby.pack(side="left",fill="both",expand=True)
        bar=ttk.Frame(f);bar.pack(anchor="e",pady=5)
        ttk.Button(bar,text="Save new hatch",command=self.save_hatch).pack(side="left",padx=3)
        ttk.Button(bar,text="Update selected",command=self.update_hatch).pack(side="left",padx=3)
        ttk.Button(bar,text="Clear",command=self.clear_hatch).pack(side="left",padx=3)
        ttk.Button(bar,text="Delete selected",command=self.delete_hatch).pack(side="left",padx=3)
        self.htree=ttk.Treeview(f,columns=("experiment","offspring","date","contributor"),show="headings",height=9)
        for col,title,w in [("experiment","Experiment",350),("offspring","Offspring",190),("date","Date",120),("contributor","Contributor",180)]:
            self.htree.heading(col,text=title);self.htree.column(col,width=w)
        self.htree.pack(fill="both",expand=True);self.htree.bind("<<TreeviewSelect>>",self.load_hatch)

    def selected_exp_id(self):
        return self.exp_choice.get(self.hexp.get())

    def pool(self,eid,category):
        if category=="Combat":
            q="""SELECT DISTINCT t.name FROM experiment_talents et JOIN talents t ON t.id=et.talent_id WHERE et.experiment_id=?"""
        else:
            q="""SELECT DISTINCT t.name FROM experiment_derby_talents et JOIN talents t ON t.id=et.talent_id WHERE et.experiment_id=?"""
        return {r[0].casefold() for r in rows(q,(eid,))}

    def load_allowed_pool(self,event=None):
        eid=self.selected_exp_id()
        if not eid:return
        combat=sorted(self.pool(eid,"Combat"))
        derby=sorted(self.pool(eid,"Derby"))
        for _,_,cb in self.hslots.items:cb["values"]=combat
        for _,_,cb in self.hderby.items:cb["values"]=[N_A]+derby

    def _hatch_values(self):
        eid=self.selected_exp_id()
        if not eid:raise ValueError("Select an experiment.")
        cv=self.hslots.get_values(required=True,allowed=self.pool(eid,"Combat"))
        dv=self.hderby.get_values(allowed=self.pool(eid,"Derby"))
        if not self.hname.get().strip():raise ValueError("Enter an offspring name.")
        return eid,cv,dv

    def save_hatch(self):
        self._save_hatch(None)

    def update_hatch(self):
        if not self.edit_hatch_id:
            messagebox.showwarning("Select hatch","Select an offspring record to update.");return
        self._save_hatch(self.edit_hatch_id)

    def _save_hatch(self,hid):
        is_edit = hid is not None
        try:
            eid,cv,dv=self._hatch_values();hid=hid or str(uuid.uuid4())
            with db() as c:
                if is_edit:
                    c.execute("UPDATE hatches SET experiment_id=?,child_name=?,hatch_date=?,contributor=?,notes=? WHERE id=?",
                              (eid,self.hname.get().strip(),self.hdate.get(),self.hcon.get(),self.hnotes.get(),hid))
                    c.execute("DELETE FROM hatch_talents WHERE hatch_id=?",(hid,))
                    c.execute("DELETE FROM hatch_derby_talents WHERE hatch_id=?",(hid,))
                else:
                    c.execute("INSERT INTO hatches VALUES(?,?,?,?,?,?,?)",(hid,eid,self.hname.get().strip(),self.hdate.get(),self.hcon.get(),self.hnotes.get(),datetime.now().isoformat()))
                c.executemany("INSERT INTO hatch_talents VALUES(?,?,?,?)",[(hid,*x) for x in cv])
                c.executemany("INSERT INTO hatch_derby_talents (hatch_id,slot,talent_id,manifested) VALUES(?,?,?,?)",[(hid,s,t,m) for s,t,m in dv])
            if not is_edit:
                self.edit_hatch_id=None
            self.refresh();messagebox.showinfo("Saved","Hatch record saved with Combat and Derby observations.")
        except Exception as e:messagebox.showerror("Hatch not saved",str(e))

    def load_hatch(self,event=None):
        sel=self.htree.selection()
        if not sel:return
        hid=sel[0];self.edit_hatch_id=hid
        r=rows("SELECT experiment_id,child_name,hatch_date,contributor,notes FROM hatches WHERE id=?",(hid,))
        if not r:return
        eid,n,d,co,no=r[0]
        self.hexp.set(next((k for k,v in self.exp_choice.items() if v==eid),""));self.load_allowed_pool()
        self.hname.set(n or "");self.hdate.set(d or "");self.hcon.set(co or "");self.hnotes.set(no or "")
        self.hslots.set_values(rows("""SELECT ht.slot,t.name,ht.manifested FROM hatch_talents ht JOIN talents t ON t.id=ht.talent_id
            WHERE ht.hatch_id=? ORDER BY ht.slot""",(hid,)))
        self.hderby.set_values(rows("""SELECT ht.slot,t.name,ht.manifested FROM hatch_derby_talents ht JOIN talents t ON t.id=ht.talent_id
            WHERE ht.hatch_id=? ORDER BY ht.slot""",(hid,)))

    def clear_hatch(self):
        self.edit_hatch_id=None
        if self.htree.selection():self.htree.selection_remove(self.htree.selection())
        self.hexp.set("");self.hname.set("");self.hdate.set(datetime.now().strftime("%Y-%m-%d"));self.hcon.set("");self.hnotes.set("")
        self.hslots.clear();self.hderby.clear()

    def delete_hatch(self):
        hid=self.edit_hatch_id or (self.htree.selection()[0] if self.htree.selection() else None)
        if not hid:return
        if not messagebox.askyesno("Delete hatch","Delete this offspring record and its Combat/Derby talent observations?"):return
        with db() as c:c.execute("DELETE FROM hatches WHERE id=?",(hid,))
        self.clear_hatch();self.refresh()

    def make_family_tree(self):
        """Build a parent-centered lineage browser for all of a pet's hatches."""
        f = self.tab("Family Tree")
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Select parent pet").pack(side="left")
        self.tree_pet = tk.StringVar()
        self.tree_pet_cb = ttk.Combobox(row, textvariable=self.tree_pet, state="readonly", width=65)
        self.tree_pet_cb.pack(side="left", fill="x", expand=True, padx=6)
        self.tree_pet_cb.bind("<<ComboboxSelected>>", lambda e: self.draw_family_tree())
        ttk.Button(row, text="Refresh", command=self.draw_family_tree).pack(side="left")

        holder = ttk.Frame(f)
        holder.pack(fill="both", expand=True, pady=8)
        self.tree_canvas = tk.Canvas(holder, background="#f4f6fa", highlightthickness=0)
        sy = ttk.Scrollbar(holder, orient="vertical", command=self.tree_canvas.yview)
        sx = ttk.Scrollbar(holder, orient="horizontal", command=self.tree_canvas.xview)
        self.tree_canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree_canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.tree_canvas.bind("<Configure>", lambda e: self.draw_family_tree())

    def _family_talents(self, table, id_column, record_id, side=None):
        """Return slot-ordered (name, manifested) rows from a talent snapshot table."""
        if side is None:
            q = f"SELECT t.name,x.manifested FROM {table} x JOIN talents t ON t.id=x.talent_id WHERE x.{id_column}=? ORDER BY x.slot"
            return rows(q, (record_id,))
        q = f"SELECT t.name,x.manifested FROM {table} x JOIN talents t ON t.id=x.talent_id WHERE x.{id_column}=? AND x.parent_side=? ORDER BY x.slot"
        return rows(q, (record_id, side))

    def draw_family_tree(self):
        """Show the selected pet, every experiment it joined, its mate, and each offspring."""
        if not hasattr(self, "tree_canvas"):
            return
        canvas = self.tree_canvas
        canvas.delete("all")
        pid = self.parent_choice.get(self.tree_pet.get())
        if not pid:
            canvas.create_text(24, 24, anchor="nw", text="Save a parent pet, then select it here to view all of its hatches.", font=("Segoe UI", 12))
            canvas.configure(scrollregion=(0, 0, 850, 260))
            return

        pet_rows = rows("SELECT name FROM pets WHERE id=?", (pid,))
        if not pet_rows:
            return
        pet_name = pet_rows[0][0]
        canvas.create_text(24, 18, anchor="nw", text=f"Family tree for: {pet_name}", font=("Segoe UI", 16, "bold"), fill="#24344d")
        experiments = rows("""SELECT e.id,e.name,e.parent_a,e.parent_b,e.created
            FROM experiments e WHERE e.parent_a=? OR e.parent_b=? ORDER BY e.created,e.name""", (pid, pid))
        if not experiments:
            canvas.create_text(28, 65, anchor="nw", text="No hatch experiments have been recorded with this pet yet.", font=("Segoe UI", 11))
            canvas.configure(scrollregion=(0, 0, 950, 260))
            return

        card_w, card_h, gap_y = 330, 350, 36
        partner_x, experiment_x, offspring_x = 390, 770, 1170
        children_gap = 290
        max_children = max((len(rows("SELECT id FROM hatches WHERE experiment_id=?", (e[0],))) for e in experiments), default=0)
        content_w = offspring_x + max(1, max_children) * children_gap + 80
        content_h = 65 + len(experiments) * (card_h + gap_y) + 30

        def talent_text(records):
            if not records:
                return "Not recorded"
            return "\n".join(name + ("  ✓ Manifested" if manifested else "") for name, manifested in records)

        for index, (eid, exp_name, parent_a, parent_b, created) in enumerate(experiments):
            top = 62 + index * (card_h + gap_y)
            selected_side = "A" if parent_a == pid else "B"
            mate_id = parent_b if selected_side == "A" else parent_a
            mate_rows = rows("SELECT name FROM pets WHERE id=?", (mate_id,))
            mate_name = mate_rows[0][0] if mate_rows else "(parent unavailable)"
            side = selected_side
            mate_side = "B" if side == "A" else "A"
            selected_combat = self._family_talents("experiment_talents", "experiment_id", eid, side)
            selected_derby = self._family_talents("experiment_derby_talents", "experiment_id", eid, side)
            mate_combat = self._family_talents("experiment_talents", "experiment_id", eid, mate_side)
            mate_derby = self._family_talents("experiment_derby_talents", "experiment_id", eid, mate_side)

            # Selected parent card anchors each experiment row; partner card shows the mate.
            canvas.create_rectangle(24, top, 24 + card_w, top + card_h, fill="#e7f1fb", outline="#47749b", width=2)
            canvas.create_text(38, top + 10, anchor="nw", text=f"SELECTED PET — {pet_name}", font=("Segoe UI", 10, "bold"), fill="#174a78")
            canvas.create_text(38, top + 34, anchor="nw", text="COMBAT\n" + talent_text(selected_combat) + "\nDERBY\n" + talent_text(selected_derby), font=("Segoe UI", 8), width=card_w - 28)

            canvas.create_rectangle(partner_x, top, partner_x + card_w, top + card_h, fill="#f1eafe", outline="#8063a6", width=2)
            canvas.create_text(partner_x + 14, top + 10, anchor="nw", text=f"HATCHED WITH — {mate_name}", font=("Segoe UI", 10, "bold"), fill="#593b80")
            canvas.create_text(partner_x + 14, top + 34, anchor="nw", text="COMBAT\n" + talent_text(mate_combat) + "\nDERBY\n" + talent_text(mate_derby), font=("Segoe UI", 8), width=card_w - 28)

            canvas.create_line(24 + card_w, top + card_h / 2, partner_x, top + card_h / 2, fill="#64748b", width=2)
            canvas.create_line(partner_x + card_w, top + card_h / 2, experiment_x, top + card_h / 2, fill="#64748b", width=2)
            canvas.create_rectangle(experiment_x, top + 132, experiment_x + 270, top + 218, fill="#fff1c7", outline="#a87916", width=2)
            canvas.create_text(experiment_x + 135, top + 175, text=f"EXPERIMENT\n{exp_name}", font=("Segoe UI", 10, "bold"), justify="center", width=250)

            hatch_rows = rows("SELECT id,child_name,hatch_date FROM hatches WHERE experiment_id=? ORDER BY created,id", (eid,))
            if not hatch_rows:
                canvas.create_line(experiment_x + 270, top + 95, offspring_x, top + 95, fill="#64748b", width=2)
                canvas.create_text(offspring_x + 10, top + 95, anchor="w", text="No offspring records yet", font=("Segoe UI", 9))
            else:
                branch_y = top + 175
                canvas.create_line(experiment_x + 270, branch_y, offspring_x, branch_y, fill="#64748b", width=2)
                if len(hatch_rows) > 1:
                    canvas.create_line(offspring_x, branch_y, offspring_x, branch_y + (len(hatch_rows) - 1) * 145, fill="#64748b", width=2)
                for child_index, (hid, child_name, hatch_date) in enumerate(hatch_rows):
                    cy = branch_y + child_index * 145 - 58
                    canvas.create_line(offspring_x, branch_y + child_index * 145, offspring_x + 18, branch_y + child_index * 145, fill="#64748b", width=2)
                    combat = self._family_talents("hatch_talents", "hatch_id", hid)
                    derby = self._family_talents("hatch_derby_talents", "hatch_id", hid)
                    canvas.create_rectangle(offspring_x + 18, cy, offspring_x + 18 + 300, cy + 130, fill="#e8f5e9", outline="#4d8a58", width=2)
                    canvas.create_text(offspring_x + 30, cy + 8, anchor="nw", text=f"OFFSPRING — {child_name or '(unnamed)'} | {hatch_date or 'Unknown date'}", font=("Segoe UI", 9, "bold"), width=280)
                    child_summary = "Combat: " + (", ".join(name + (" ✓" if m else "") for name, m in combat) or "Not recorded")
                    child_summary += "\nDerby: " + (", ".join(name + (" ✓" if m else "") for name, m in derby) or "N/A — no Derby talents recorded")
                    canvas.create_text(offspring_x + 30, cy + 38, anchor="nw", text=child_summary, font=("Segoe UI", 8), width=280)

        # Account for all offspring branches, including experiments with many hatch records.
        for i, (eid, *_rest) in enumerate(experiments):
            count = len(rows("SELECT id FROM hatches WHERE experiment_id=?", (eid,)))
            content_h = max(content_h, 62 + i * (card_h + gap_y) + card_h + max(0, count - 1) * 145 + 40)
        canvas.configure(scrollregion=(0, 0, content_w, content_h))

    def make_analytics(self):
        f=self.tab("Analytics")
        row=ttk.Frame(f);row.pack(fill="x")
        ttk.Label(row,text="Experiment scope").pack(side="left")
        self.scope=tk.StringVar(value="All experiments")
        self.scope_cb=ttk.Combobox(row,textvariable=self.scope,state="readonly",width=75);self.scope_cb.pack(side="left",padx=6)
        ttk.Button(row,text="Refresh",command=self.refresh_analytics).pack(side="left")
        self.asummary=ttk.Label(f);self.asummary.pack(anchor="w",pady=5)
        panes=ttk.Panedwindow(f,orient="vertical");panes.pack(fill="both",expand=True)
        for cat in ("Combat","Derby"):
            frame=ttk.Labelframe(panes,text=f"{cat} analytics",padding=5);panes.add(frame,weight=1)
            tree=ttk.Treeview(frame,columns=("count","rate"),show="tree headings",height=9)
            tree.heading("#0",text="Talent");tree.heading("count",text="Offspring with talent");tree.heading("rate",text="Share of hatches")
            tree.column("#0",width=420);tree.column("count",width=180);tree.column("rate",width=160)
            tree.pack(fill="both",expand=True)
            if cat=="Combat":self.acombat=tree
            else:self.aderby=tree

    def refresh_analytics(self):
        if not hasattr(self,"acombat"):return
        for tree in (self.acombat,self.aderby):
            for x in tree.get_children():tree.delete(x)
        eid=self.exp_choice.get(self.scope.get())
        hs=rows("SELECT id FROM hatches"+(" WHERE experiment_id=?" if eid else ""),((eid,) if eid else ()))
        total=len(hs); counts={"Combat":{},"Derby":{}}
        for (hid,) in hs:
            for cat,table in (("Combat","hatch_talents"),("Derby","hatch_derby_talents")):
                for (name,) in rows(f"SELECT t.name FROM {table} x JOIN talents t ON t.id=x.talent_id WHERE x.hatch_id=?",(hid,)):
                    counts[cat][name]=counts[cat].get(name,0)+1
        self.asummary.config(text=f"{total} offspring records in selected scope. Combat and Derby counts are calculated independently.")
        for cat,tree in (("Combat",self.acombat),("Derby",self.aderby)):
            for name,n in sorted(counts[cat].items(),key=lambda x:(-x[1],x[0].casefold())):
                tree.insert("","end",text=name,values=(n,f"{n/total:.1%}" if total else "0%"))

    def make_catalog(self):
        f=self.tab("Talent Catalog")
        row=ttk.Frame(f);row.pack(fill="x")
        self.search=tk.StringVar();ttk.Label(row,text="Search").pack(side="left")
        ttk.Entry(row,textvariable=self.search,width=35).pack(side="left",padx=5)
        self.search.trace_add("write",lambda *_:self.refresh_catalog())
        ttk.Button(row,text="Add talent",command=self.add_talent).pack(side="left",padx=4)
        ttk.Button(row,text="Import talent CSV",command=self.import_talents).pack(side="left",padx=4)
        self.ttree=ttk.Treeview(f,columns=("category","school","rarity","status","notes"),show="tree headings")
        self.ttree.heading("#0",text="Talent");self.ttree.column("#0",width=300)
        for col,w in [("category",90),("school",120),("rarity",100),("status",100),("notes",500)]:
            self.ttree.heading(col,text=col.title());self.ttree.column(col,width=w)
        self.ttree.pack(fill="both",expand=True,pady=8)
        ttk.Label(f,text="Combat and Derby remain separate categories. Catalog imports preserve all supplied metadata.").pack(anchor="w")

    def add_talent(self):
        w=tk.Toplevel(self);w.title("Add talent");fields={}
        for i,(label,default) in enumerate([("Name",""),("Category","Combat"),("School","Universal"),("Rarity",""),("Status","Active"),("Notes","")]):
            ttk.Label(w,text=label).grid(row=i,column=0,padx=8,pady=4,sticky="w")
            v=tk.StringVar(value=default);fields[label]=v
            if label=="Category":ttk.Combobox(w,textvariable=v,values=("Combat","Derby"),state="readonly").grid(row=i,column=1,padx=8,pady=4)
            else:ttk.Entry(w,textvariable=v,width=48).grid(row=i,column=1,padx=8,pady=4)
        def save():
            try:
                if not fields["Name"].get().strip():raise ValueError("Name required.")
                with db() as c:c.execute("INSERT INTO talents(name,category,school,rarity,status,notes) VALUES(?,?,?,?,?,?)",
                    tuple(fields[k].get().strip() for k in ("Name","Category","School","Rarity","Status","Notes")))
                w.destroy();self.refresh()
            except Exception as e:messagebox.showerror("Cannot add",str(e),parent=w)
        ttk.Button(w,text="Save",command=save).grid(row=6,column=1,pady=6)

    def import_talents(self):
        p=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not p:return
        try:
            n=0
            with open(p,encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    name=(r.get("name") or r.get("Talent") or "").strip()
                    if name:
                        cat=(r.get("category") or "Combat").strip()
                        with db() as c:
                            c.execute("""INSERT INTO talents(name,category,school,rarity,status,notes)
                                VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                                category=excluded.category,school=excluded.school,rarity=excluded.rarity,
                                status=excluded.status,notes=excluded.notes""",
                                (name,cat,r.get("school","") or "",r.get("rarity","") or "",r.get("status","Active") or "Active",r.get("notes","") or ""))
                        n+=1
            self.refresh();messagebox.showinfo("Import",f"Imported/updated {n} catalog rows.")
        except Exception as e:messagebox.showerror("CSV import failed",str(e))

    def make_data(self):
        f=self.tab("Import / Export")
        ttk.Label(f,text="Research dataset sharing and backups",font=("Segoe UI",15,"bold")).pack(anchor="w",pady=6)
        ttk.Label(f,text="JSON includes both talent categories, all parent/experiment/hatch observations, metadata, and snapshots.",wraplength=1000).pack(anchor="w")
        bar=ttk.Frame(f);bar.pack(anchor="w",pady=15)
        ttk.Button(bar,text="Export complete database (JSON)",command=self.export_json).pack(side="left",padx=4)
        ttk.Button(bar,text="Import research JSON",command=self.import_json).pack(side="left",padx=4)
        ttk.Button(bar,text="Export all hatch talents (CSV)",command=self.export_csv).pack(side="left",padx=4)
        ttk.Button(bar,text="Export catalog CSV",command=self.export_catalog).pack(side="left",padx=4)
        ttk.Button(bar,text="Backup SQLite database",command=self.backup).pack(side="left",padx=4)
        self.dstatus=ttk.Label(f);self.dstatus.pack(anchor="w",pady=8)
        ttk.Label(f,text=f"Live database: {DB}",foreground="#555").pack(anchor="w",pady=12)

    def export_json(self):
        p=filedialog.asksaveasfilename(defaultextension=".json",initialfile="wizard101_pet_research.json",filetypes=[("JSON","*.json")])
        if not p:return
        data={"format":"wizard101-pet-genetics","version":2,"exported_at":datetime.now().isoformat()}
        tables=["talents","pets","pet_talents","pet_derby_talents","experiments","experiment_talents","experiment_derby_talents","hatches","hatch_talents","hatch_derby_talents"]
        with db() as c:
            for t in tables:
                cols=[x[1] for x in c.execute(f"PRAGMA table_info({t})")]
                data[t]=[dict(zip(cols,r)) for r in c.execute(f"SELECT * FROM {t}")]
        Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        self.dstatus.config(text=f"Exported complete dataset: {p}")

    def import_json(self):
        p=filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not p:return
        try:
            data=json.loads(Path(p).read_text(encoding="utf-8"))
            if data.get("format")!="wizard101-pet-genetics":raise ValueError("Unsupported file format.")
            if not messagebox.askyesno("Merge data","Merge this research dataset? Existing matching IDs/names are preserved."):return
            tables=["talents","pets","pet_talents","pet_derby_talents","experiments","experiment_talents","experiment_derby_talents","hatches","hatch_talents","hatch_derby_talents"]
            counts={}
            with db() as c:
                # Talent IDs are database-local. Map incoming IDs by name so
                # existing catalog rows with different numeric IDs remain valid.
                talent_id_map={}
                counts["talents"]=0
                for talent in data.get("talents",[]):
                    incoming_id=talent.get("id")
                    name=(talent.get("name") or "").strip()
                    if not name:
                        continue
                    existing=c.execute("SELECT id FROM talents WHERE name=? COLLATE NOCASE",(name,)).fetchone()
                    if existing:
                        local_id=existing[0]
                    else:
                        cols=[k for k in talent if k in {"id","name","category","school","rarity","status","notes"}]
                        try:
                            cur=c.execute(f"INSERT INTO talents ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                                          [talent[k] for k in cols])
                        except sqlite3.IntegrityError:
                            # Reassign an incoming numeric ID if another local talent uses it.
                            fields=[k for k in cols if k!="id"]
                            cur=c.execute(f"INSERT INTO talents ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                                          [talent[k] for k in fields])
                        local_id=c.execute("SELECT id FROM talents WHERE name=? COLLATE NOCASE",(name,)).fetchone()[0]
                        counts["talents"]+=cur.rowcount
                    if incoming_id is not None:
                        talent_id_map[incoming_id]=local_id
                for t in tables[1:]:
                    counts[t]=0
                    for r in data.get(t,[]):
                        record=dict(r)
                        if "talent_id" in record and record["talent_id"] in talent_id_map:
                            record["talent_id"]=talent_id_map[record["talent_id"]]
                        cols=list(record)
                        if not cols:
                            continue
                        cur=c.execute(f"INSERT OR IGNORE INTO {t} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                                      [record[k] for k in cols])
                        counts[t]+=cur.rowcount
            self.refresh();messagebox.showinfo("Import complete","\n".join(f"{k}: {v}" for k, v in counts.items()))
        except Exception as e:messagebox.showerror("Import failed",str(e))

    def export_csv(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv",initialfile="wizard101_hatches_all_talents.csv",filetypes=[("CSV","*.csv")])
        if not p:return
        data=[]
        for cat,table in (("Combat","hatch_talents"),("Derby","hatch_derby_talents")):
            data += [(cat,*r) for r in rows(f"""SELECT e.name,h.id,h.child_name,h.hatch_date,h.contributor,x.slot,t.name,x.manifested
                FROM {table} x JOIN hatches h ON h.id=x.hatch_id JOIN experiments e ON e.id=h.experiment_id
                JOIN talents t ON t.id=x.talent_id ORDER BY e.name,h.created,x.slot""")]
        with open(p,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f);w.writerow(["category","experiment","hatch_id","offspring","date","contributor","slot","talent","manifested"]);w.writerows(data)
        self.dstatus.config(text=f"Exported {len(data)} Combat/Derby talent-slot rows.")

    def export_catalog(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv",initialfile="talent_catalog.csv",filetypes=[("CSV","*.csv")])
        if not p:return
        with open(p,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.writer(f);w.writerow(["name","category","school","rarity","status","notes"])
            w.writerows(rows("SELECT name,category,school,rarity,status,notes FROM talents ORDER BY category,name"))
        self.dstatus.config(text=f"Exported catalog CSV: {p}")

    def backup(self):
        p=filedialog.asksaveasfilename(defaultextension=".sqlite3",initialfile="pet_genetics_backup.sqlite3",filetypes=[("SQLite","*.sqlite3")])
        if p:shutil.copy2(DB,p);self.dstatus.config(text=f"Backup saved to {p}")

    def refresh_catalog(self):
        if not hasattr(self,"ttree"):return
        for x in self.ttree.get_children():self.ttree.delete(x)
        q=self.search.get().casefold()
        for n,cat,school,rarity,status,notes in rows("SELECT name,category,school,rarity,status,notes FROM talents ORDER BY category,name"):
            if q and not any(q in (v or "").casefold() for v in (n,cat,school,rarity,status,notes)):continue
            self.ttree.insert("","end",text=n,values=(cat,school,rarity,status,notes or ""))

    def refresh(self):
        """Refresh record lists, selectors, and catalog-driven views."""
        if not hasattr(self,"parents"):return
        for tree in (self.parents,self.exptree,self.htree):
            for item in tree.get_children():tree.delete(item)
        prs=rows("SELECT id,name FROM pets ORDER BY name")
        for pid,n in prs:self.parents.insert("","end",iid=pid,values=(n,))
        previous_tree_pet = self.tree_pet.get() if hasattr(self, "tree_pet") else ""
        self.parent_choice={f"{n} [{pid[:8]}]":pid for pid,n in prs}
        if hasattr(self, "tree_pet_cb"):
            self.tree_pet_cb["values"] = list(self.parent_choice)
            if previous_tree_pet in self.parent_choice:
                self.tree_pet.set(previous_tree_pet)
            elif self.parent_choice:
                self.tree_pet.set(next(iter(self.parent_choice)))
            else:
                self.tree_pet.set("")
        self.eacb["values"]=list(self.parent_choice);self.ebcb["values"]=list(self.parent_choice)
        exps=rows("""SELECT e.id,e.name,a.name,b.name,e.contributor FROM experiments e
            LEFT JOIN pets a ON a.id=e.parent_a LEFT JOIN pets b ON b.id=e.parent_b ORDER BY e.created DESC""")
        self.exp_choice={f"{n} — {a or 'Missing parent'} × {b or 'Missing parent'} [{eid[:8]}]":eid for eid,n,a,b,co in exps}
        self.hcb["values"]=list(self.exp_choice)
        self.scope_cb["values"]=["All experiments"]+list(self.exp_choice)
        for eid,n,a,b,co in exps:self.exptree.insert("","end",iid=eid,values=(f"{n}: {a} × {b}",co or ""))
        for hid,en,cn,dt,co in rows("""SELECT h.id,e.name,h.child_name,h.hatch_date,h.contributor FROM hatches h
            JOIN experiments e ON e.id=h.experiment_id ORDER BY h.created DESC"""):
            self.htree.insert("","end",iid=hid,values=(en,cn,dt,co or ""))
        for editor in (self.pslots,self.pderby,self.hslots,self.hderby):editor.refresh_values()
        self.refresh_catalog();self.refresh_analytics()
        self.draw_family_tree()

if __name__=="__main__":
    init()
    App().mainloop()
