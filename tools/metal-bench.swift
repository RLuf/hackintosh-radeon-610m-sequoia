// metal-bench: carga de computação para medir o clock da GPU pelo tempo.
// Uso: metal-bench [repetições=20] [iterações por elemento=2048]
// Cada elemento faz `iter` FMAs encadeadas (2 FLOPs cada) sobre 1M floats; mede o tempo de GPU de cada despacho.
import Metal
import Foundation

let args = CommandLine.arguments
let reps = args.count > 1 ? Int(args[1]) ?? 20 : 20
let iter = args.count > 2 ? Int(args[2]) ?? 2048 : 2048
let n = 1 << 20

guard let dev = MTLCreateSystemDefaultDevice() else { print("ERRO: sem dispositivo Metal (boot sem aceleração?)"); exit(1) }
print("dispositivo: \(dev.name)")
let src = """
#include <metal_stdlib>
using namespace metal;
kernel void fma_loop(device float *b [[buffer(0)]], constant uint &iter [[buffer(1)]], uint i [[thread_position_in_grid]]) {
    float x = b[i], y = 1.0001f, z = 0.9999f;
    for (uint k = 0; k < iter; k++) { x = fma(x, y, z); y = fma(y, z, x * 1e-7f); }
    b[i] = x + y;
}
"""
do {
    let lib = try dev.makeLibrary(source: src, options: nil)
    let pso = try dev.makeComputePipelineState(function: lib.makeFunction(name: "fma_loop")!)
    guard let q = dev.makeCommandQueue(),
          let buf = dev.makeBuffer(length: n * 4, options: .storageModeShared) else { print("ERRO: fila/buffer"); exit(1) }
    var it = UInt32(iter)
    let flops = Double(n) * Double(iter) * 4.0  // 2 FMAs por volta = 4 FLOPs
    var tempos: [Double] = []
    for r in 0..<reps {
        guard let cb = q.makeCommandBuffer(), let enc = cb.makeComputeCommandEncoder() else { print("ERRO: cb"); exit(1) }
        enc.setComputePipelineState(pso)
        enc.setBuffer(buf, offset: 0, index: 0)
        enc.setBytes(&it, length: 4, index: 1)
        let tg = min(pso.maxTotalThreadsPerThreadgroup, 256)
        enc.dispatchThreads(MTLSize(width: n, height: 1, depth: 1), threadsPerThreadgroup: MTLSize(width: tg, height: 1, depth: 1))
        enc.endEncoding()
        let t0 = Date()
        cb.commit()
        cb.waitUntilCompleted()
        let parede = Date().timeIntervalSince(t0) * 1000
        let gpu = (cb.gpuEndTime - cb.gpuStartTime) * 1000
        if cb.status != .completed { print("ERRO: status \(cb.status.rawValue) \(String(describing: cb.error))"); exit(2) }
        let ms = gpu > 0 ? gpu : parede
        tempos.append(ms)
        print(String(format: "rep %2d: gpu %.2f ms (parede %.2f ms), %.2f GFLOPS", r + 1, gpu, parede, flops / (ms / 1000) / 1e9))
    }
    let ord = tempos.sorted()
    let med = ord[ord.count / 2]
    print(String(format: "RESUMO: %d reps, %d iter, mediana %.2f ms = %.2f GFLOPS, melhor %.2f ms", reps, iter, med, flops / (med / 1000) / 1e9, ord[0]))
} catch { print("ERRO: \(error)"); exit(1) }
