# 📊 COMPARACIÓN: Antes vs Después

## ANTES (Incorrecto)

```
┌─────────────────────────────────────────────────────┐
│ Frontend: Usuario crea un participante nuevo        │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
         ❌ POST /api/asignarTablasConsecutivas
         Con "participante_id" (que NO existe aún)
         
         Error: Participante no encontrado
         
```

## AHORA (Correcto)

```
┌──────────────────────────────────────────────────────────┐
│ Frontend: Usuario está creando un participante nuevo    │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
       ✅ POST /api/obtenerTablasConsecutivas
       {
         "usuario_id": "...",
         "cantidad_tablas": 2
       }
       
       Respuesta:
       {
         "tablas_consecutivas": ["CARD004", "CARD005"],
         "cantidad": 2
       }
       
                     │
                     ▼
       Mostrar en el formulario:
       "Se asignarán: CARD004 y CARD005"
       
                     │
                     ▼
       Usuario confirma y hace submit
       
                     │
                     ▼
       ✅ POST /api/registrarParticipante
       {
         "nombre": "Juan",
         "apellido": "Pérez",
         "cedula": "1234567",
         "tablas": ["CARD004", "CARD005"],  ← LOS QUE OBTUVIMOS
         "registrado_por": "..."
       }
       
       Respuesta: ✅ Participante creado exitosamente
       
```

## Tabla Comparativa

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Endpoint** | `/api/asignarTablasConsecutivas` | `/api/obtenerTablasConsecutivas` |
| **Requiere participante_id** | ❌ Sí (error) | ✅ No |
| **Parámetros** | usuario_id, participante_id, cantidad, tipo | usuario_id, cantidad |
| **Modifica BD** | ❌ Sí | ✅ No |
| **Retorna** | Tablas asignadas + IDs | Solo códigos de tablas |
| **Cuándo usar** | ??? | Al crear participante |
| **Flujo** | ❌ Lógico inverso | ✅ Lógico correcto |

## Diferencia Técnica

### Antes: POST /api/asignarTablasConsecutivas
```python
# Requería que el participante YA EXISTIERA
participante = mongo_collection_participantes.find_one({"_id": participante_obj_id})
if not participante:
    return 404  # ❌ Error: participante no existe
```

### Ahora: POST /api/obtenerTablasConsecutivas
```python
# Solo verifica que el usuario existe
usuario = mongo_collection_users.find_one({"_id": usuario_obj_id})
if not usuario:
    return 404  # Usuario no existe (está bien)

# Obtiene y devuelve los códigos SIN asignarlos
tablas_disponibles = [...]
return jsonify({"tablas_consecutivas": ["CARD004", "CARD005"]})
```

## ¿Cuándo usar cada endpoint?

| Situación | Endpoint |
|-----------|----------|
| Crear participante NUEVO | 1. `/api/obtenerTablasConsecutivas` → 2. `/api/registrarParticipante` |
| Agregar más tablas a participante EXISTENTE | `/api/participante/{id}/tablas/{tipo}` |
| Solo consultar código disponibles | `/api/obtenerTablasConsecutivas` |
| Validar disponibilidad | `/api/obtenerTablasConsecutivas` |

## Ejemplo Real: Caso de Uso Completo

```javascript
// ESCENARIO: Crear participante en el frontend

// ====== PASO 1: Consultar tablas disponibles ======
const obtenerTablas = async () => {
  const res = await fetch('/api/obtenerTablasConsecutivas', {
    method: 'POST',
    body: JSON.stringify({
      usuario_id: usuarioId,
      cantidad_tablas: 2
    })
  });
  
  const datos = await res.json();
  if (datos.success) {
    // Mostrar en UI
    document.getElementById('tablas-asignar').textContent = 
      datos.tablas_consecutivas.join(', ');
    // Guardar para usar después
    window.tablasAsignar = datos.tablas_consecutivas;
  }
};

// ====== PASO 2: Crear el participante ======
const crearParticipante = async (formData) => {
  const res = await fetch('/api/registrarParticipante', {
    method: 'POST',
    body: JSON.stringify({
      nombre: formData.nombre,
      apellido: formData.apellido,
      cedula: formData.cedula,
      tablas: window.tablasAsignar,  // ← Usar las que obtuvimos en PASO 1
      registrado_por: usuarioId
    })
  });
  
  const resultado = await res.json();
  if (resultado.success) {
    alert('✅ Participante creado con tablas: ' + window.tablasAsignar.join(', '));
  }
};

// ====== USO ======
// Usuario: "Necesito crear un participante con 2 tablas"
await obtenerTablas();  // Se muestran CARD004, CARD005
// Usuario: "OK, crear el participante"
await crearParticipante(formData);  // Se crea con esas tablas
```

## ✅ Checklist: Lo que necesitas hacer

- [ ] Actualizar tu frontend para usar `/api/obtenerTablasConsecutivas`
- [ ] Guardar los códigos devueltos antes de crear el participante
- [ ] Enviar esos códigos en `/api/registrarParticipante`
- [ ] Probar el flujo completo
- [ ] Verificar que las tablas se asignan correctamente

---

**Resumen:** Ahora el flujo es más lógico: primero obtienes los códigos, luego creas el participante con ellos. ✨
